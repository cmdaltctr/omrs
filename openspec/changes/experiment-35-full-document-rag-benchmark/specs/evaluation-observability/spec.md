# evaluation-observability Specification

## ADDED Requirements

### Requirement: The benchmark is a Confirmatory publication experiment

Experiment 35 SHALL have purpose `publication` and size Confirmatory. `preregistration.md`, `protocol.md` and `plan.json` SHALL be committed before the first measured run. From amendment A4 (2026-11-14), `preregistration.md` SHALL govern the live design: where another file of the experiment or this change differs from it, `preregistration.md` SHALL win. After the freeze, every change SHALL be a dated, numbered deviation, added to the `plan.json` `amendments` list and uploaded to OSF.

#### Scenario: A measured run starts before the plan is committed
- **WHEN** the run record shows a plan file that differs from the committed `plan.json`
- **THEN** the run SHALL NOT count as a measured result

#### Scenario: Two files disagree on a design fact
- **WHEN** `design.md` or `plan.json` states a design fact that differs from `preregistration.md`
- **THEN** the `preregistration.md` value SHALL apply
- **AND** the other file SHALL be corrected before the freeze

### Requirement: Local models are pinned and checked before scoring

`plan.json` SHALL hold an ADR-103 `runtime` block. Every local model SHALL run through llama.cpp with a public GGUF file, pinned by repository, file, SHA-256, build and server arguments, with a tolerance per primary metric. Hosted models SHALL appear only as named reference arms.

#### Scenario: The live server differs from the plan
- **WHEN** `verify_llamacpp_runtime` finds a different build or file hash
- **THEN** the run SHALL stop before the first score is written

#### Scenario: The run moves to other hardware
- **WHEN** a run uses rented cloud hardware instead of the local Mac
- **THEN** it SHALL use the same GGUF files and build, and SHALL apply the planned tolerance
- **AND** all arms of one dataset SHALL run on the same machine and back end

### Requirement: Answer setups run three times with a determinism check

Each index SHALL be built once, and each search setup SHALL run once (run 1) for the scored retrieval result. Each answer setup SHALL run 3 times, and each answer run's retrieval SHALL be compared with the search stage. Per dataset, the `e4b-c1024` index SHALL be rebuilt once in a fresh process and compared. The report SHALL state the determinism result and the run-to-run standard deviation of answers, judge scores and latency.

#### Scenario: Retrieval differs between runs
- **WHEN** an answer run retrieves a different ranked list from the search stage for any question
- **THEN** the report SHALL record the mismatch and its size
- **AND** another run SHALL NOT replace run 1 as the scored result

#### Scenario: Paired tests use repeated runs
- **WHEN** two answer setups are compared
- **THEN** the 3 runs SHALL be averaged per question before questions are paired

### Requirement: Spending stops at a stated ceiling with a results-blind drop order

The protocol SHALL state a cost estimate and a ceiling, pods and hosted calls together (about $730 and $975, `preregistration.md` section 17). Projections SHALL use billing and measured rates only, never scores, before the freeze, after the search stage and while the replicate pods run. At the ceiling, work SHALL be dropped in a results-blind order fixed before the run, and no confirmatory item SHALL be dropped by choice.

#### Scenario: Projection above the ceiling
- **WHEN** a projection, from measured index and search hours, reaches the ceiling
- **THEN** the run SHALL drop the next step in this order and compute the projection again: (1) Legal RAG Bench answer generation, (2) the length-controlled check, (3) the closed-book run with the RAG prompt
- **AND** E1 SHALL NOT be in this order, because it has its own ceiling
- **AND** the run record SHALL name the projection that triggered each step

#### Scenario: Drop order exhausted
- **WHEN** the projection still reaches the ceiling after step (3)
- **THEN** the run SHALL stop
- **AND** no operator choice SHALL select what is dropped

#### Scenario: Run finishes after drop steps
- **WHEN** every confirmatory item is done after one or more drop steps
- **THEN** the run SHALL be reported as "complete with registered drops", and each drop SHALL be a numbered deviation
- **AND** a run SHALL be reported as incomplete only when a confirmatory item is missing

#### Scenario: Closed-book RAG-prompt run dropped
- **WHEN** step (3) drops the closed-book run with the RAG prompt
- **THEN** the contamination sensitivity SHALL use the own-knowledge closed-book run alone, and the report SHALL say so

### Requirement: Statistics follow the pre-registered analysis

The analysis SHALL follow `preregistration.md` section 9 and SHALL fit no mixed model. Each contrast row SHALL use per-question contrast scores (cells weighted equally, answer scores averaged over 3 runs first), and the estimate SHALL be their plain mean. The report SHALL give unadjusted 95% intervals beside each decision, marked against the SESOI and the minimum detectable effect.

#### Scenario: Test on FreshStack, BioASQ or Legal RAG Bench
- **WHEN** a row's p-value and interval are computed on FreshStack, BioASQ or Legal RAG Bench
- **THEN** they SHALL come from the closed form of pre-registration section 9 point 3: the mean of the contrast scores, the Mancl and DeRouen bias-reduced variance (sum of squared residuals times (n / (n minus 1)) squared, divided by n squared) and a t reference on n minus 1 degrees of freedom
- **AND** the `statsmodels` GEE implementation (intercept only, independence working correlation, question clusters, `cov_type="bias_reduced"`) SHALL be checked against that closed form by a known-answer test, and the closed form SHALL be used if they differ

#### Scenario: Test on FinanceBench
- **WHEN** a row's p-value and interval are computed on FinanceBench
- **THEN** they SHALL come from a document-level sign-flip permutation test with 100,000 draws and seed 20261101

#### Scenario: No difference found
- **WHEN** the Holm-adjusted p is 0.05 or more
- **THEN** the report SHALL state that no difference was detected at this sample size
- **AND** the report SHALL NOT claim equivalence, and no TOST SHALL run

#### Scenario: Decision and sensitivity check disagree
- **WHEN** a row counts under the decision test but not under its sensitivity check (paired permutation by question on FreshStack and BioASQ, GEE with document clusters on FinanceBench), or the other way
- **THEN** the report SHALL list the row in one disagreement table, and the decision test SHALL decide

#### Scenario: New statistics code is written
- **WHEN** the analysis needs a statistic
- **THEN** it SHALL use the functions in `experiments/_lib/stats.py` or the s-experiment reference `stats.py`, or a tested function added for this analysis

### Requirement: Holm families are fixed before the run

Holm correction (alpha 0.05) SHALL run within families of fixed size: FinanceBench 19 rows, FreshStack 19 rows and BioASQ 8 rows (rows 1 to 8; rows 9 to 19 are sanity checks, pending open item O6), 46 in all. Legal RAG Bench SHALL have no family. No gate decided on main-run labels SHALL change a family size.

#### Scenario: A gate fails
- **WHEN** the faithfulness gate of GLM-5.3 fails
- **THEN** rows 12, 13, 16 and 17 SHALL stay in every Holm family with p = 1 and be reported as not testable
- **AND** the other rows SHALL keep the same number of comparisons

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

### Requirement: Faithfulness checkers pass a registered gate

Each faithfulness checker SHALL pass when Cohen's kappa against the human label has a point estimate of at least 0.60 and a lower 95% bound of at least 0.40, on 450 claims (150 per chunk size) from answers to all questions, pooled over the core datasets. Each gate interval SHALL be a percentile bootstrap (10,000 resamples by question, own seed). Gate decisions SHALL be recorded, with their time, before any H8 contrast result is computed. There SHALL be no cross-check judge.

#### Scenario: The judge configuration changes
- **WHEN** the judge model, its settings or the Ragas version changes
- **THEN** the resulting scores SHALL belong to a new evaluation revision

#### Scenario: Checker specificity differs by chunk size
- **WHEN** the 95% interval of the GLM-5.3 specificity difference (2,048 minus 512) excludes zero in either direction
- **THEN** H8a and H8b faithfulness rows 12, 13, 16 and 17 SHALL be exploratory and reported as not testable

#### Scenario: The second checker fails its gate
- **WHEN** Clef-Flash fails its faithfulness gate
- **THEN** its results SHALL be reported as not validated and SHALL change no confirmatory row

### Requirement: Human labels follow the registered counts

L1 SHALL label 750 items (claim kinds 100, faithfulness 450 from all questions, correctness 200 from half B), and L2 SHALL label a 30% subset of each set (225 items). The claim classifier SHALL reach agreement of at least 0.90 and refusal recall of at least 0.90 on 100 L1-labelled smoke claims before the freeze.

#### Scenario: A label file is released
- **WHEN** human labels are released
- **THEN** they SHALL carry the roles L1 and L2 only, and no labeller name SHALL appear

### Requirement: Outputs respect dataset licences

`output/` SHALL be split into shareable and restricted parts. Releases SHALL follow the release table of `preregistration.md` section 19, each artefact under its dataset's licence, and SHALL NOT hold corpus text, PDFs or derived text. FinanceBench-derived files SHALL NOT be released under CC BY. Each dataset's derived files SHALL go in their own Zenodo archive with their own licence.

#### Scenario: Corpus text reaches a shareable folder
- **WHEN** a file under the shareable part of `output/` contains corpus text
- **THEN** the release check SHALL fail before any upload

#### Scenario: A reader judges the answers again
- **WHEN** a reader wants to judge the released answers with a newer model
- **THEN** the re-judge kit SHALL rebuild the evidence text from the pinned dataset revisions and the released IDs

### Requirement: Public releases carry an example set and no personal identifiers

The release SHALL include a small shareable example input set with expected output and a reading guide. Before the repository or any release goes public, names, login names and home-folder paths SHALL be removed and the upload searched for them.

#### Scenario: A home-folder path is found in a release
- **WHEN** the pre-release search finds a home-folder path or a personal name
- **THEN** the release SHALL NOT be uploaded until it is removed

### Requirement: Hosted calls record the model that answered

Every hosted call SHALL record the model id and provider that the reply returns, beside the requested ones. The report SHALL count differences per role, and the raw verdicts SHALL be released where the licence allows.

#### Scenario: Provider routes to another model
- **WHEN** a reply names another model than the one requested
- **THEN** the row SHALL keep both names, and the join SHALL count it

### Requirement: The protocol is publicly pre-registered

`preregistration.md` (main file), `protocol.md`, `plan.json`, the proposal and the Part 2 protocol of the freeze commit SHALL be deposited on OSF. A later commit, made before the first measured run, SHALL record the OSF link and the freeze commit hash in the `plan.json` `frozen` list with the other pins of `preregistration.md` section 16; the freeze commit cannot hold its own hash. The A3 configuration hash SHALL be time-stamped on the registered OSF project before any half-B score is computed.

#### Scenario: Run before the deposit
- **WHEN** the first measured run starts and `plan.json` `frozen` holds no OSF link
- **THEN** the freeze SHALL count as incomplete

#### Scenario: Half-B score before the time stamp
- **WHEN** a half-B score is computed before the A3 configuration hash is time-stamped on OSF
- **THEN** the run SHALL record a deviation, and the RQ1 headline SHALL state it
