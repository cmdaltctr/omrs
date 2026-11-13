## Purpose

Defines how a benchmark run scores its answers: parallel hosted answers over serial retrieval, the Ragas stage of the main harness, and the frozen classifier that keeps refusal sentences out of the primary claim scores and reports them apart.

## ADDED Requirements

### Requirement: Parallel answers keep serial retrieval

The answer stage SHALL retrieve the evidence of each question one question at a time, with the same search arguments as the search stage. Only the hosted answer call SHALL run in parallel. The evidence of an answer SHALL NOT depend on the answer concurrency.

#### Scenario: Same evidence at any concurrency

- **WHEN** one answer stage runs on stub calls at concurrency 8 and again at concurrency 1
- **THEN** each question MUST have the same evidence chunk IDs in both runs, in the same order

#### Scenario: Retrieval failure

- **WHEN** retrieval fails for one question
- **THEN** the stage MUST keep that question's row with the error and MUST NOT send an answer call for it

### Requirement: Ragas is a stage of the main harness

The harness SHALL have a `ragas` stage that scores the answers of one run folder on the machine that ran that run. It SHALL use the pre-freeze Ragas version, judge and settings, the four pre-freeze metrics plus `AnswerCorrectness` against the reference answer, with embeddings from the local llama.cpp server and the plan's pinned 4B embedding file. It SHALL need the finished answer stage of that run, and SHALL write one row per answer in frozen question order.

#### Scenario: One run folder

- **WHEN** the operator runs the `ragas` stage for one dataset, arm and run
- **THEN** the stage MUST read only that run folder's answers and MUST write its rows and done-marker in that run folder

#### Scenario: Answer stage not finished

- **WHEN** the `ragas` stage starts and the answer stage of that run has no done-marker
- **THEN** the stage MUST refuse to start before any call

#### Scenario: Embedding server differs from the plan

- **WHEN** the local embedding server reports another llama.cpp build or another file hash than the plan
- **THEN** the stage MUST stop before any paid call and MUST name the difference

#### Scenario: Wrong Ragas version

- **WHEN** the installed Ragas version differs from the frozen version
- **THEN** the stage MUST stop before any paid call and MUST name both versions

#### Scenario: Failed answer

- **WHEN** an answer row holds an error or no answer text
- **THEN** the Ragas row of that question MUST record that it was not judged, and the stage MUST send no call for it

### Requirement: Concurrent Ragas answers keep their own call records

When the Ragas stage scores several answers at once, each answer's row SHALL hold only the calls and metric labels of that answer. No call record SHALL move to the row of another answer.

#### Scenario: Two answers at once

- **WHEN** two answers are scored at the same time and their calls interleave
- **THEN** each row MUST list only its own calls, each with the metric it belongs to

### Requirement: Ragas resume never repeats a paid call

A Ragas row SHALL be saved only when every metric of the answer has a score or an error that is not a rate limit. With `--resume`, the stage SHALL skip each answer that has a saved row. A rate-limit error SHALL NOT be saved as a metric result.

#### Scenario: Resume after a stop

- **WHEN** the stage stopped after 40 of 100 answers had saved rows
- **THEN** `--resume` MUST send calls only for the other 60 answers

#### Scenario: Rate limit during a metric

- **WHEN** a metric call fails with HTTP 429 on every attempt
- **THEN** no row for that answer MUST be saved, and the stage MUST stop with the rate-limit exit code

### Requirement: Claim sentences are sorted by a frozen classifier

A `claimkinds` stage SHALL give each judged claim of one run folder one kind from a frozen classifier: factual claim, refusal, or mixed. A refusal states only that the sources do not cover something. A mixed sentence holds a checkable fact and a scope limit, and SHALL count as a factual claim. A negative finding that answers the question SHALL be a factual claim. Each output SHALL name the classifier version.

#### Scenario: Refusal

- **WHEN** a claim says only that the sources do not cover the question
- **THEN** the classifier MUST give the kind refusal

#### Scenario: Negative finding

- **WHEN** a claim says "no debt securities are listed" in answer to a question about listed debt securities
- **THEN** the classifier MUST give the kind factual claim

#### Scenario: Mixed sentence

- **WHEN** a claim states a figure from the sources and adds that the sources give no later year
- **THEN** the classifier MUST give the kind mixed, and the figures MUST count it as a factual claim

#### Scenario: One run folder

- **WHEN** the `claimkinds` stage runs for one dataset, arm and run
- **THEN** it MUST read only that run folder's answers and judge rows, and MUST write the kinds and a done-marker in that run folder

#### Scenario: Version names the classifier

- **WHEN** a claim kind is saved
- **THEN** it MUST carry the classifier version, which identifies the pinned model, the host, the prompt, the reasoning level, the temperature and the seed

#### Scenario: Classifier input

- **WHEN** the classifier sorts a claim
- **THEN** it MUST receive the question and the claim sentence only, and never the evidence or a verdict

#### Scenario: Claim count differs

- **WHEN** the claims split from a saved answer do not match the number of verdicts in its judge row
- **THEN** the classification MUST stop and MUST name the dataset, arm, run and question

#### Scenario: Resume

- **WHEN** the classification stopped part-way and runs again with `--resume`
- **THEN** it MUST classify only the claims without a saved kind

### Requirement: The classifier passes a hand-label gate before the freeze

Before the freeze, the operator SHALL label a seeded sample of about 100 smoke claims from the three smoke datasets, blind to the classifier's output and to every verdict. The pass thresholds SHALL be fixed before labelling starts. The classifier SHALL be frozen only when it passes; a failed gate SHALL block the freeze of the classifier.

#### Scenario: Thresholds fixed first

- **WHEN** the labelling page is opened for the first time
- **THEN** the protocol MUST already state the pass thresholds: agreement on refusal against not refusal of at least 0.90, and refusal recall of at least 0.90

#### Scenario: Same sample twice

- **WHEN** the gate sample is drawn twice with the same seed
- **THEN** the two samples MUST hold the same claims in the same order, and the labelling page MUST show no kind and no verdict

#### Scenario: Gate fails

- **WHEN** the refusal recall on the gate sample is below 0.90
- **THEN** the gate result MUST say fail, and the classifier MUST NOT be marked frozen

### Requirement: Primary scores use factual claims only

Primary faithfulness, per answer setup and per checker (GLM-5.3 and Clef-Flash), SHALL use factual claims only (kinds factual claim and mixed).

#### Scenario: Refusal claims present

- **WHEN** an answer setup has refusal claims
- **THEN** its primary faithfulness MUST leave them out

### Requirement: Refusals are reported separately

A refusal report step SHALL read a joined main run and SHALL refuse to start without a passing join report. It SHALL give the refusal rate per answer setup and dataset as a primary descriptive outcome. For refusal claims only, it SHALL give each checker's unsupported rate and the Cohen's kappa of Clef-Flash against GLM-5.3. For factual claims, it SHALL give the Cohen's kappa of Clef-Flash against GLM-5.3 per dataset.

#### Scenario: Refusal tables

- **WHEN** the refusal report runs on a joined main run
- **THEN** it MUST write a refusal-rate table with one row per answer setup and dataset, and a refusal-verdict table with one row per checker and dataset

### Requirement: All-claims robustness check

The report SHALL give, as a secondary robustness result, faithfulness per answer setup and dataset on all claims, refusals included. These figures SHALL NOT replace the primary figures.

#### Scenario: All-claims figures

- **WHEN** the refusal report runs
- **THEN** it MUST write the all-claims faithfulness beside the primary figures, labelled as a robustness result

### Requirement: Per-checker refusal bounds

For each checker separately, the report SHALL recompute faithfulness on all claims with that checker's refusal verdicts all supported, then all unsupported. It SHALL report the lowest and highest faithfulness per answer setup and dataset that each checker's bounds give, as a secondary robustness result.

#### Scenario: Clef-Flash bounds

- **WHEN** the bounds run for Clef-Flash
- **THEN** only Clef-Flash's refusal verdicts MUST change, and the report MUST give the lowest and highest faithfulness per answer setup and dataset from the two settings

### Requirement: Answer correctness is checked against hand labels

A sampling step SHALL draw 100 answers with seed 20261113, 25 per dataset, even over the chunk sizes, and SHALL write them without any Ragas score. An agreement step SHALL binarise `AnswerCorrectness` at 0.5 and SHALL give Cohen's kappa against the operator labels per dataset and pooled, and whether the pooled kappa reaches 0.60.

#### Scenario: Same sample twice

- **WHEN** the sample is drawn twice with the same seed
- **THEN** both samples MUST hold the same answers in the same order, with no score shown

#### Scenario: Kappa below the rule

- **WHEN** the pooled kappa is 0.55
- **THEN** the agreement report MUST mark answer correctness exploratory

### Requirement: A closed-book run checks contamination

A `closedbook` stage SHALL answer every question once with no retrieval and SHALL score it with `AnswerCorrectness` and the FinanceBench number match. The report SHALL show RAG correctness split by retrieval hit or miss beside closed-book correctness.

#### Scenario: No search call

- **WHEN** the closed-book stage runs
- **THEN** it MUST send no search call and MUST pass an empty evidence list

### Requirement: Every answer is one synthesis round

Each answer setup, the closed-book run and the oracle run SHALL run with `answer.context_window` 131,072 characters and `answer.max_rounds` 1.

#### Scenario: Evidence needs two rounds

- **WHEN** a test synthesises the largest evidence set of an answer setup and OMRS makes a second completion call
- **THEN** the test MUST fail and name the setup

### Requirement: Answer rows record rounds and truncation

Each answer row SHALL record the number of synthesis rounds, the evidence characters and, from OMRS's own evidence-fit function applied to the same rows and settings, the number of truncated evidence passages and the characters dropped. A test SHALL show, before the freeze, that the largest evidence set of every answer setup synthesises without a context overflow.

#### Scenario: Evidence cut at 2,048 tokens

- **WHEN** an answer's evidence does not fit the round budget and OMRS cuts a passage
- **THEN** the answer row MUST record one truncated passage and the characters dropped, and the answer MUST still be saved

#### Scenario: Largest evidence set

- **WHEN** the pre-freeze test synthesises the question with the most evidence characters of a 2,048-token answer setup through a stub seam
- **THEN** no round MUST fail with a context overflow error

### Requirement: Ragas answer scores keep refusals

The Ragas stage SHALL score every answer, refusal answers included, with no special handling. Whether a refusal lowers a Ragas score SHALL be stated in the protocol only from the frozen Ragas version's source, not assumed.

#### Scenario: Refusal answer scored

- **WHEN** an answer is a pure refusal
- **THEN** the Ragas stage MUST score it with every metric, as for any other answer
