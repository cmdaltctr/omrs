## Purpose

Shared experiment code under `experiments/_lib/` that later experiments import to compare rankings and neighbour lists and to write timing outputs, so a fix lands once and a closed experiment's folder stays as it ran.

## ADDED Requirements

### Requirement: Reused harness code lives in the shared library

Harness code that more than one experiment uses SHALL live in `experiments/_lib/` with its tests. A closed experiment's folder SHALL keep the code it ran with, unchanged. A later experiment SHALL import the shared code and SHALL NOT copy it.

#### Scenario: Experiment 48 stays as it ran

- **WHEN** the shared library takes over the ranking, neighbour and timing helpers
- **THEN** no file in `experiments/48-pipeline-sweep-llamacpp-2026-11-01/` MUST change, and its own tests MUST still pass

### Requirement: Neighbour lists never hold the query chunk

The top-k neighbour comparison SHALL use each chunk as a query against the other chunks of its slice. The neighbour list SHALL NOT contain the query chunk, whatever the slice size. On a slice with k or fewer chunks, each list SHALL hold all the other chunks.

#### Scenario: Small slice

- **WHEN** a slice holds 5 chunks and k is 10
- **THEN** each neighbour list MUST hold exactly the 4 other chunks and MUST NOT hold the query chunk

#### Scenario: Large slice unchanged

- **WHEN** a slice holds 50 chunks and k is 10
- **THEN** each neighbour list MUST hold 10 chunks, none of them the query chunk, in the same order as before this change

### Requirement: Output files are written atomically

Every output file the timing and fast-mode steps write SHALL be written to a temporary file in the same folder and then renamed into place. A run stopped part-way SHALL leave either the old file or no file, never a partial one.

#### Scenario: Stop during a vector file write

- **WHEN** the fast-mode step fails while it writes a vector file
- **THEN** the target path MUST hold either the earlier complete file or nothing

### Requirement: The determinism comparison covers every question of both runs

The ranking comparison SHALL compare the union of the questions in run 1 and run 2. A question present in only one run SHALL be reported as a mismatch.

#### Scenario: Question only in run 2

- **WHEN** run 2 holds a ranking for question `q9` and run 1 holds none
- **THEN** the comparison MUST report a mismatch for `q9`

#### Scenario: Question only in run 1

- **WHEN** run 1 holds a ranking for question `q4` and run 2 holds none
- **THEN** the comparison MUST report a mismatch for `q4`

### Requirement: A relative model folder is resolved at once

The folder of GGUF files named by the harness environment SHALL be turned into an absolute path when it is read. A folder that does not exist SHALL be refused there, with a message that names the variable and the path.

#### Scenario: Relative path

- **WHEN** the model-folder variable is `models/gguf` and the run starts in a folder that contains it
- **THEN** the harness MUST use the absolute path of that folder for every later step, even after the working folder changes

#### Scenario: Missing folder

- **WHEN** the model-folder variable names a folder that does not exist
- **THEN** the harness MUST stop before any model starts, naming the variable and the path
