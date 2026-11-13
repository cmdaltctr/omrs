## Purpose

Lets a benchmark build its indexes once and run its repetitions on separate machines against one shared, read-only index, then join the runs and check them before determinism and statistics.

## ADDED Requirements

### Requirement: The build step records an index fingerprint

The harness SHALL have a seal step that runs after one index is built. It SHALL refuse to run while that index has no finished ingest on a dataset. It SHALL write a fingerprint per index and dataset: the table version, the dataset epoch and the full-text index state (row counts, or none). The seal step SHALL NOT create or refresh a full-text index.

#### Scenario: Fingerprint after the build

- **WHEN** the seal step runs for an index whose ingest is finished on every dataset
- **THEN** the output folder MUST hold a fingerprint for that index on each dataset

#### Scenario: Index not built

- **WHEN** the seal step runs and the `e8b-c2048` index of a dataset has no finished ingest
- **THEN** the seal step MUST stop with a setup error that names the index and the dataset, and MUST write no fingerprint

#### Scenario: Native full-text index checked, not built

- **WHEN** a hybrid-on setup's resolved sparse backend is `native`
- **THEN** the seal step MUST refuse and name the collection when the full-text index that the OMRS ingest built is missing or has unindexed rows, and MUST leave the table version unchanged

#### Scenario: BM25 hybrid setup

- **WHEN** a hybrid-on setup's resolved sparse backend is `bm25`
- **THEN** the fingerprint MUST record the resolved backend and no full-text index state for that setup

### Requirement: A replicate stage never writes to the shared index

A search, answer or judge stage SHALL check the index fingerprint before its first query and again after its last. It SHALL refuse to start when the fingerprint is missing or differs, or when a full-text index it needs is missing or holds unindexed rows. A change found at the end SHALL fail the stage without a done-marker.

#### Scenario: Missing full-text index

- **WHEN** a hybrid search stage with the `native` sparse backend starts and the full-text index of its collection is missing
- **THEN** the stage MUST refuse to start before any query, and MUST name the collection, because OMRS would fall back to BM25 for that query

#### Scenario: Sparse backend differs from the seal

- **WHEN** a hybrid stage resolves another sparse backend than the one the fingerprint records
- **THEN** the stage MUST refuse to start before any query and MUST name both backends

#### Scenario: Hybrid search after the seal

- **WHEN** a hybrid search stage runs on a sealed collection
- **THEN** the table version and the full-text index row counts of that collection MUST be the same after the stage as in the fingerprint

#### Scenario: Index changed during the stage

- **WHEN** the table version of a collection differs at the end of a stage from the fingerprint
- **THEN** the stage MUST exit with a setup error and MUST NOT write its done-marker

### Requirement: Machine-local state and settings

The harness SHALL accept a machine-local folder for the router state (`OMRS_STATE_DIR`) and the scratch settings of each process. With that folder set, a stage SHALL write its state and settings there and SHALL NOT write them under the shared output folder. Without it, the harness SHALL keep the current layout.

#### Scenario: Two machines share one output folder

- **WHEN** runs 2 and 3 run at the same time on two machines with the same output folder and their own local folders
- **THEN** each process MUST write router state and settings only in its own local folder, and MUST write run outputs only under its own `run<n>/` folders

#### Scenario: Default layout kept

- **WHEN** no local folder is named
- **THEN** state and settings MUST go to the same folders as before this change

### Requirement: One environment for every stage

Each build machine SHALL write an environment record: GPU model, container image, llama.cpp build and the SHA-256 of each plan GGUF file. Every stage that runs a model, sends a model call or reads the index SHALL record its own and SHALL refuse to start when it differs from the build record. The join SHALL fail a run whose record differs. Steps that only read saved files SHALL NOT need the record.

#### Scenario: Stage on another environment

- **WHEN** a Ragas stage starts on a machine whose GPU model differs from the build record
- **THEN** the stage MUST stop before any call and MUST name the differing field

#### Scenario: Join finds a different environment

- **WHEN** the run record of run 2 holds a machine record whose llama.cpp build or GGUF hash differs from the build pod's record
- **THEN** the join report MUST fail and MUST name the run and the differing field

#### Scenario: Image not pinned by digest

- **WHEN** a stage starts and the recorded image reference has no `@sha256:` digest
- **THEN** the stage MUST stop before any call and MUST say that the image must be pinned by digest

#### Scenario: Report on saved files

- **WHEN** the refusal report runs on a laptop from the copied-back run files
- **THEN** it MUST run without an environment record

### Requirement: Index builds run on parallel pods with separate stores

Each index SHALL be buildable on its own pod. An index pod SHALL write only to its own store folder for that index on the shared volume, and SHALL seal and search only its own index. Two pods SHALL never write to one store.

#### Scenario: Nine pods at once

- **WHEN** nine index pods build `e0.6b-c512` to `e8b-c2048` at the same time on one network volume
- **THEN** each store folder MUST be written by one pod only, and each fingerprint MUST match its store after all nine finish

### Requirement: Every main-run pod uses one GPU type

The GPU type SHALL be chosen before the freeze by the rule written in the protocol: among GPUs that hold the 8B embedder and the 8B reranker together without swapping, the lowest projected GPU cost for the index builds and the 72 search setups, and the faster GPU when two are within 10% on cost. Every main-run pod SHALL use that type. A stage SHALL refuse to start when its GPU model differs from the build record.

#### Scenario: Replicate pod on another GPU

- **WHEN** the index pods ran on an L40S and a replicate pod starts on an RTX 4090
- **THEN** its first stage MUST stop before any call and MUST name the GPU model field

### Requirement: Each run records the machine that ran it

Each run folder SHALL hold a machine record for each stage start: the host name, the pod identifier when one is set, and the environment record. The determinism report SHALL list the machine of each run, so that a retrieval match across runs is also a match across machines.

#### Scenario: Runs on three pods

- **WHEN** runs 1, 2 and 3 of an arm ran on three pods
- **THEN** the determinism report MUST name the three machines beside the retrieval result

### Requirement: Each machine keeps its own run records

Each replicate machine SHALL append its run records to its own file. The join step SHALL merge the records of every machine into the experiment's run-record file by appending only. It SHALL NOT change or reorder an earlier line, and SHALL NOT add a line that the file already holds.

#### Scenario: Merge twice

- **WHEN** the join step merges the same three machine files twice
- **THEN** the experiment's run-record file MUST gain each machine line once, and its earlier lines MUST stay unchanged

### Requirement: The join step gates determinism and statistics

The join step SHALL check that run 1 of every search setup and dataset has a finished search stage (search runs once per setup), that runs 1, 2 and 3 of every answer setup and dataset have finished answer, judge, `ragas` and `claimkinds` stages, that every run has the same run key, that every run has a run record, and that every stage found the index fingerprint unchanged. It SHALL write a join report. Determinism and statistics SHALL refuse to start without a passing join report.

#### Scenario: One stage missing

- **WHEN** run 3 of the answer setup `e4b-c1024-r0.6b-hon` on FinanceBench has no finished `chat` judge stage
- **THEN** the join report MUST fail and MUST name the dataset, arm, run and stage

#### Scenario: Search checked on run 1 only

- **WHEN** every search setup has a finished `search` stage in run 1 and none in runs 2 and 3
- **THEN** the join MUST NOT fail for a missing search stage, because search runs once per setup

#### Scenario: Ragas rows incomplete

- **WHEN** run 1 of an arm has `ragas` rows for fewer answers than its answer stage holds, or no `ragas` done-marker
- **THEN** the join report MUST fail and MUST name the dataset, arm, run and stage

#### Scenario: Smoke join with one run

- **WHEN** the join step runs on a smoke folder with only run 1 and a smoke flag
- **THEN** it MUST check that run's stages, keys, records and environment, and MUST write a join report marked smoke that determinism and statistics refuse

#### Scenario: Determinism before the join

- **WHEN** the determinism stage starts and no passing join report exists
- **THEN** the stage MUST refuse to start and MUST name the join step

#### Scenario: Different question sets

- **WHEN** run 2 of an arm has another run key than run 1
- **THEN** the join report MUST fail and MUST name the differing fields

### Requirement: A smoke run can name its questions

The harness SHALL accept a list of question IDs. A run with that list SHALL use only those questions, in frozen order, and SHALL count as a smoke run: it SHALL write no line to the experiment's run-record file. An ID that is not in the dataset SHALL stop the run before any call.

#### Scenario: Two named questions

- **WHEN** the operator runs the answer stage of FreshStack with the IDs `77536364` and `77762811`
- **THEN** the stage MUST answer only those two questions and MUST write no run record

#### Scenario: Unknown question ID

- **WHEN** a named ID is not in the dataset
- **THEN** the run MUST stop with a setup error that names the ID, before any call

### Requirement: A run can read its index from another folder

The harness SHALL accept an index folder apart from the output folder. A run with it SHALL read the store, the index markers and the fingerprint from that folder, and SHALL write its outputs only to the output folder. The index folder SHALL be read-only for that run.

#### Scenario: Recheck against the shared index

- **WHEN** a named-question smoke run reads its index from the shared folder and writes to a smoke folder
- **THEN** the shared folder MUST gain no file, and the smoke folder MUST hold the run outputs

### Requirement: The rebuild check compares retrieval from a rebuilt index

The build machine SHALL build the baseline index of each dataset a second time, in a fresh process and a separate store. A comparison step SHALL compare, question by question, the ranked IDs that the rebuilt index retrieves with those that the shared index retrieves. It SHALL write a rebuild report per dataset and SHALL exit with the mismatch exit code when any question differs.

#### Scenario: Same lists

- **WHEN** every question retrieves the same ranked IDs from both indexes
- **THEN** the rebuild report MUST say the check passed, with the number of questions compared

#### Scenario: One list differs

- **WHEN** one question retrieves IDs in another order from the rebuilt index
- **THEN** the rebuild report MUST name that question, and the step MUST exit with the mismatch exit code

#### Scenario: Question missing on one side

- **WHEN** a question has a search row from only one of the two indexes
- **THEN** the rebuild report MUST count it as a mismatch

#### Scenario: Failed rebuild check stops the replicate runs

- **WHEN** a search, answer or judge stage starts that writes run outputs into the shared output folder, and its dataset's rebuild report is missing or failed
- **THEN** the stage MUST stop before any query or call and MUST name the dataset and the rebuild report

#### Scenario: Join checks the rebuild report

- **WHEN** the join step runs and a dataset has no rebuild report
- **THEN** the join report MUST fail and MUST name the dataset
