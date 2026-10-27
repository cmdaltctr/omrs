# evaluation-observability Specification

## ADDED Requirements

### Requirement: The benchmark is a Confirmatory publication experiment

Experiment 35 SHALL have purpose `publication` and size Confirmatory. Its `protocol.md` and `plan.json` SHALL be committed before the first measured run. Later changes SHALL be recorded only as plan amendments.

#### Scenario: A measured run starts before the plan is committed
- **WHEN** the run record shows a plan file that differs from the committed `plan.json`
- **THEN** the run SHALL NOT count as a measured result

### Requirement: Local models are pinned and checked before scoring

`plan.json` SHALL hold an ADR-103 `runtime` block. Every local model SHALL run through llama.cpp with a public GGUF file, pinned by repository, file, SHA-256, build and server arguments, with a tolerance per primary metric. Hosted models SHALL appear only as named reference arms.

#### Scenario: The live server differs from the plan
- **WHEN** `verify_llamacpp_runtime` finds a different build or file hash
- **THEN** the run SHALL stop before the first score is written

#### Scenario: The run moves to other hardware
- **WHEN** a run uses rented cloud hardware instead of the local Mac
- **THEN** it SHALL use the same GGUF files and build, and SHALL apply the planned tolerance
- **AND** all arms of one dataset SHALL run on the same machine and back end

### Requirement: Each arm runs three times with a determinism check

Each arm SHALL run 3 times. Run 1 SHALL give the scored retrieval result, and runs 2 and 3 SHALL be compared with it. The report SHALL state the result of the determinism check and the run-to-run standard deviation of answers, judge scores and latency.

#### Scenario: Retrieval differs between runs
- **WHEN** run 2 or run 3 retrieves a different ranked list from run 1 for any question
- **THEN** the report SHALL record the mismatch and its size
- **AND** another run SHALL NOT replace run 1 as the scored result

#### Scenario: Paired tests use repeated runs
- **WHEN** an arm is compared with the baseline
- **THEN** the 3 runs SHALL be averaged per question before questions are paired

### Requirement: Statistics follow the frozen basic set

For each dataset and arm the report SHALL give the mean with a 95% interval, the paired difference from the baseline with a 95% interval, a paired permutation test for scores, McNemar's exact test for hit or miss, Holm correction across arms, and wins, losses and ties. The minimum detectable effect SHALL be stated before the run.

#### Scenario: No difference is found
- **WHEN** the Holm-adjusted p is 0.05 or more, or the paired interval includes zero
- **THEN** the report SHALL state that no difference larger than the minimum detectable effect was found

#### Scenario: New statistics code is written
- **WHEN** the analysis needs a statistic
- **THEN** it SHALL use the functions in `experiments/_lib/stats.py` or the s-experiment reference `stats.py`

### Requirement: The benchmark emits structured stage traces

The harness SHALL emit secret-free JSONL records for each query and major stage, with run ID, arm, repetition, question ID, model identities, retrieved IDs, stage durations and error or degraded status. Trace output SHALL NOT be written to the MCP stdout channel.

#### Scenario: A query fails during retrieval
- **WHEN** retrieval raises or degrades
- **THEN** the trace SHALL record the stage, elapsed time, status and question identity
- **AND** the question SHALL remain in the benchmark denominator

### Requirement: Run identity is sufficient for reproducibility

Each measured run SHALL record the benchmark revision, OMRS commit, dirty-tree flag, plan SHA-256, effective settings, model identities with file hashes, dependency-lock identity, index identity and hardware.

#### Scenario: Two runs use different embedding files
- **WHEN** the embedding file hashes differ
- **THEN** the run records SHALL expose that difference
- **AND** the results SHALL NOT be treated as the same arm

### Requirement: Ragas is a secondary, evaluation-only layer

Ragas 0.4.3 MAY score faithfulness, answer relevancy, context precision and context recall. Its version, judge model and settings SHALL be pinned, with temperature 0. Ragas SHALL be declared only in a separate `uv` dependency group, never in the base install or a published extra.

#### Scenario: Ragas is added to a published extra
- **WHEN** `pyproject.toml` lists Ragas under `[project.optional-dependencies]` or `[project].dependencies`
- **THEN** the change SHALL be rejected

#### Scenario: Ragas is unavailable
- **WHEN** the evaluation environment does not contain Ragas
- **THEN** primary retrieval metrics SHALL remain runnable
- **AND** Ragas metrics SHALL be reported as not measured

### Requirement: Judge scores are checked by hand

About 50 Ragas-judged items SHALL be checked by hand, with the agreement measure defined in the protocol before the check. The report SHALL state the agreement. The judge SHALL run through llama.cpp when possible.

#### Scenario: The judge configuration changes
- **WHEN** the judge model, its settings or the Ragas version changes
- **THEN** the resulting scores SHALL belong to a new evaluation revision

### Requirement: Outputs respect dataset licences

`output/` SHALL be split into shareable and restricted parts. Releases SHALL hold scores, question IDs and rebuild scripts, not corpus text. FinanceBench-derived files SHALL NOT be released under CC BY. Each dataset's derived files SHALL go in their own Zenodo archive with their own licence.

#### Scenario: Corpus text reaches a shareable folder
- **WHEN** a file under the shareable part of `output/` contains corpus text
- **THEN** the release check SHALL fail before any upload

### Requirement: Public releases carry an example set and no personal identifiers

The release SHALL include a small shareable example input set with expected output and a reading guide. Before the repository or any release goes public, names, login names and home-folder paths SHALL be removed and the upload searched for them.

#### Scenario: A home-folder path is found in a release
- **WHEN** the pre-release search finds a home-folder path or a personal name
- **THEN** the release SHALL NOT be uploaded until it is removed
