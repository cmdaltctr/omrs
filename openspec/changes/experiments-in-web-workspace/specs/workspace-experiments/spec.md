# Spec Delta

## MODIFIED Requirements

### Requirement: Experiment contexts group under named folders

The Experiments view SHALL have a Sandboxes section that groups experiment contexts under their parent directories below the approved experiment roots, showing named main folders that each list their sub-experiments. A main folder with no contexts SHALL still be listed. When no root is approved, the section SHALL say so and name the `--experiment-root` server flag.

#### Scenario: Grouped listing

- **WHEN** two contexts exist under `reranker-calibration` and one under `input-quality`
- **THEN** the view MUST show both folders with their contexts listed beneath them

#### Scenario: Empty folder

- **WHEN** a main folder exists on disk with no registered context
- **THEN** the folder MUST appear with an empty indication

### Requirement: Marimo loads through plugin approval

The Experiments view SHALL have a Code editor section that keeps the notebook tool registration, trust notice, one-time credentials and editor launch panels. Opening a notebook editor for an experiment workspace SHALL launch the registered marimo tool, and stopping it SHALL end the launch.

#### Scenario: Open the marimo editor

- **WHEN** marimo is registered and the user opens the editor for an experiment workspace
- **THEN** an editor launch MUST start and its status MUST be shown with a stop action

## ADDED Requirements

### Requirement: Experiments sections

The Experiments view SHALL offer the sections Library, Notebooks, Sandboxes, Code editor and Runs, and SHALL open on Library. The library experiment page SHALL have the address `#/experiments/library/<project-id>/<folder>`, and a notebook page SHALL have the address `#/experiments/notebooks/<notebook-id>`, so that a reload shows the same page.

#### Scenario: Default section

- **WHEN** the user opens `#/experiments`
- **THEN** the Library section is shown

#### Scenario: Reload an experiment page

- **WHEN** the user reloads `#/experiments/library/<project-id>/<folder>`
- **THEN** that experiment page is shown
