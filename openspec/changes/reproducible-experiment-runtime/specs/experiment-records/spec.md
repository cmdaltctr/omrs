## MODIFIED Requirements

### Requirement: Every experiment has a versioned record file

Each experiment folder SHALL contain an `experiment.json` record that declares the format `omrs-experiment/1`. The record SHALL hold the experiment number, title, date, category, size, status, the folder that supersedes it, a one-line finding, an optional purpose, optional references to decision records, changes and tasks, and an optional migration note. The record SHALL reject keys that format version 1 does not define.

#### Scenario: Unknown key

- **WHEN** an `experiment.json` contains a key that format version 1 does not define
- **THEN** loading fails with a message that names the key

#### Scenario: Newer format version

- **WHEN** an `experiment.json` declares a format version that this release does not know
- **THEN** loading fails with a message that names the version and says a newer `omrs` is needed

### Requirement: Record fields take only allowed values

The number SHALL be one or more digits, optionally followed by one lower-case letter or by a dot and digits (`22`, `5b`, `10.1`), or empty for an unnumbered experiment. The category SHALL be one of `retrieval`, `ingestion`, `runtime`, `generation`, `graph`, `review`. The size SHALL be one of `Quick`, `Standard`, `Confirmatory`. The purpose, when present, SHALL be one of `optimisation`, `publication`. The finding SHALL be one line.

#### Scenario: Valid record

- **WHEN** an `experiment.json` declares `omrs-experiment/1` and has every required field with an allowed value
- **THEN** the record loads without error

#### Scenario: Unknown purpose

- **WHEN** an `experiment.json` sets `purpose` to a value other than `optimisation` or `publication`
- **THEN** loading fails with a message that names the field and the allowed values

## ADDED Requirements

### Requirement: Every experiment has a purpose

An experiment SHALL have one of two purposes. `optimisation` means the result tunes this project and is not cited outside it. `publication` means the result may be cited in a paper. A record without the `purpose` field SHALL count as `optimisation`.

#### Scenario: Old record without a purpose

- **WHEN** a record written before this change has no `purpose` field
- **THEN** it loads without error and counts as `optimisation`
- **AND** the checker reports nothing about the missing field

### Requirement: New records state their purpose

The folder creator SHALL write the purpose into every new record. It SHALL use `optimisation` when no purpose is given.

#### Scenario: New experiment without a purpose option

- **WHEN** a new experiment is created and no purpose is given
- **THEN** its `experiment.json` holds `"purpose": "optimisation"`

### Requirement: Paper results come from new publication experiments

A past experiment SHALL NOT be changed to `publication`. A result that a paper needs SHALL come from a new `publication` follow-up that re-runs the experiment.

#### Scenario: Publication follow-up of an old experiment

- **WHEN** a `publication` follow-up of experiment 38 is created
- **THEN** the new folder `38a` holds `"purpose": "publication"`
- **AND** the record of experiment 38 is not changed

### Requirement: The checker enforces the publication rules

The checker SHALL report an error for a `publication` experiment that does not meet each of these rules. The size SHALL be `Confirmatory`. `plan.json` SHALL hold a `runtime` block that meets the local-runtime rule of the experiment validity gates. A `publication` record whose `plan.json` cannot be read SHALL fail the runtime check. The checker SHALL NOT apply these rules to an `optimisation` experiment or to a record without a purpose. Each finding SHALL name the folder and the rule it breaks.

#### Scenario: Publication experiment of the wrong size

- **WHEN** a record has `"purpose": "publication"` and `"size": "Standard"`
- **THEN** the checker reports an error that names the folder and says a publication experiment must be Confirmatory

#### Scenario: Publication experiment without a runtime block

- **WHEN** a Confirmatory `publication` experiment has a `plan.json` with no `runtime` block
- **THEN** the checker reports an error that names the folder and the missing block

#### Scenario: Optimisation experiment without a runtime block

- **WHEN** an `optimisation` experiment has a `plan.json` with no `runtime` block
- **THEN** the checker reports no error about the runtime
