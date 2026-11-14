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

### Requirement: Ragas resume never repeats a saved answer's calls

A Ragas row SHALL be saved only when every metric of the answer has a score or an error that is not a rate limit. With `--resume`, the stage SHALL skip each answer that has a saved row. A rate-limit error SHALL NOT be saved as a metric result. An answer whose row was not saved SHALL be scored again in full on resume, so its earlier metric calls repeat; this affects at most one answer per worker per stop, the same bound as the claim judge (design risks).

#### Scenario: Resume after a stop

- **WHEN** the stage stopped after 40 of 100 answers had saved rows
- **THEN** `--resume` MUST send calls only for the other 60 answers

#### Scenario: Rate limit during a metric

- **WHEN** a metric call fails with HTTP 429 on every attempt
- **THEN** no row for that answer MUST be saved, and the stage MUST stop with the rate-limit exit code
- **AND** `--resume` MUST score that answer again with every metric

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

#### Scenario: Claim still unclassified after resume

- **WHEN** the classifier still fails on a claim after `--resume`
- **THEN** the claim MUST count as a factual claim, stay in the faithfulness denominator and be counted
- **AND** a sensitivity analysis MUST leave such claims out

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

### Requirement: Uncited segments are reported and tested in a sensitivity analysis

Primary faithfulness SHALL cover cited factual claims only. The report SHALL give, per setup and dataset, the share of prose segments with no valid ordinal. The classifier SHALL also sort uncited segments, with the question and segment only. A registered sensitivity analysis SHALL count uncited fact and mixed segments as unsupported (pre-registration section 6; open item O7).

#### Scenario: One cited and one uncited fact

- **WHEN** an answer holds one cited fact the checker calls supported and one uncited segment the classifier calls fact
- **THEN** primary faithfulness MUST be 1.0, the sensitivity MUST be 0.5, and the uncited share MUST be 0.5

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

### Requirement: Answer correctness passes a gate per core dataset

A sampling step SHALL draw 50 half-B questions per dataset with seed 20261113, each with the run-1 answer of an answer setup the seed picks uniformly, with no Ragas score shown. A core dataset passes only when Cohen's kappa of `AnswerCorrectness` cut at 0.5 against the human labels has a point estimate of at least 0.60 and a lower 95% bound of at least 0.40, with "can't tell" scored both ways (both must pass), and the AUC of the continuous score has a lower 95% bound above 0.5.

#### Scenario: Same sample twice

- **WHEN** the sample is drawn twice with the same seed
- **THEN** both samples MUST hold the same answers in the same order, with no score shown

#### Scenario: Gate interval method

- **WHEN** the agreement step computes any gate interval (kappa, AUC or specificity difference)
- **THEN** it MUST use a percentile bootstrap with 10,000 resamples by question and the seed listed for that interval in pre-registration section 16

#### Scenario: Statistic undefined on the full sample

- **WHEN** the labelled sample of a dataset holds only one human class, so the AUC or kappa is undefined
- **THEN** the gate MUST fail on that dataset

#### Scenario: Undefined resamples

- **WHEN** a resample holds only one class
- **THEN** the step MUST NOT draw it again, MUST give it kappa 0 or AUC 0.5, and MUST count it
- **AND** the gate MUST fail when more than 500 of the 10,000 resamples are undefined

#### Scenario: Point estimate passes but lower bound fails

- **WHEN** kappa on FinanceBench is 0.65 with a lower 95% bound of 0.35
- **THEN** the gate MUST fail on FinanceBench

#### Scenario: Continuous score fails

- **WHEN** kappa on FreshStack passes and the lower 95% bound of the AUC is 0.48
- **THEN** the gate MUST fail on FreshStack

### Requirement: A failed correctness gate keeps its rows in the family

A failed correctness gate SHALL mark rows 14, 15, 18 and 19 "not testable" on that dataset, with p = 1 in its Holm family. Legal RAG Bench labels SHALL be reported with no gate. Prevalence, raw agreement and PABAK SHALL be reported beside kappa. The gate SHALL be recorded with its time before any H8a or H8b contrast result is computed.

#### Scenario: Gate fails on one dataset only

- **WHEN** the gate fails on BioASQ and passes on FinanceBench and FreshStack
- **THEN** rows 14, 15, 18 and 19 MUST stay testable on FinanceBench and FreshStack, and the BioASQ result MUST change no family, because BioASQ rows 12 to 19 are sanity checks

### Requirement: Faithfulness checkers pass a gate per checker

A sampling step SHALL draw 450 claims from crossed-setup answers to all questions (both halves) with seed 20261116: 150 per chunk size, 50 per core dataset within each, at most one claim per answer, with no verdict shown. A checker's gate SHALL pass when Cohen's kappa against the human label, with "can't tell" as not supported, has a point estimate of at least 0.60 and a lower 95% bound of at least 0.40. If GLM-5.3 fails, rows 12, 13, 16 and 17 SHALL be "not testable" on every dataset.

#### Scenario: Faithfulness sample spans both halves

- **WHEN** the sampling step draws the faithfulness sample
- **THEN** it MUST draw from answers to questions in both half A and half B, because H8a and H8b are tested on all questions
- **AND** the correctness sample MUST still come from half B only

#### Scenario: Second checker fails its gate

- **WHEN** Clef-Flash fails its kappa gate
- **THEN** its results MUST be reported as not validated and MUST change no confirmatory row

#### Scenario: Kappa also without can't tell

- **WHEN** the agreement step reports a checker's kappa
- **THEN** it MUST also report kappa with the "can't tell" items left out, and that value MUST NOT decide the gate

### Requirement: A differential-error rule guards H8a and H8b faithfulness

The agreement step SHALL give each checker's specificity (the share of human-supported claims it calls supported) and sensitivity per chunk size. When the 95% interval of the GLM-5.3 specificity difference (2,048 minus 512) excludes zero in either direction, rows 12, 13, 16 and 17 SHALL be "not testable", with p = 1 in their families. The gate record SHALL carry its time, and no H8a and H8b faithfulness row SHALL be computed before it exists.

#### Scenario: Specificity differs by chunk size

- **WHEN** GLM-5.3 passes its kappa gate and the 95% interval of its specificity difference (2,048 minus 512) excludes zero, whether the difference is below or above zero
- **THEN** rows 12, 13, 16 and 17 MUST be "not testable", and the family sizes MUST NOT change

#### Scenario: Second checker specificity differs

- **WHEN** only the Clef-Flash specificity difference excludes zero
- **THEN** it MUST be reported only and MUST NOT change any row

#### Scenario: Specificity difference undefined

- **WHEN** a chunk-size level of the full sample, or of more than 500 of the 10,000 resamples, holds no human-supported claim
- **THEN** rows 12, 13, 16 and 17 MUST be "not testable"
- **AND** a resample with no human-supported claim at a level MUST NOT be drawn again, MUST be left out of the interval and MUST be counted

#### Scenario: Gate decided before H8a and H8b results

- **WHEN** the analysis starts an H8a or H8b faithfulness row and no gate record with a time exists
- **THEN** it MUST refuse and MUST name the gate step

### Requirement: A length-controlled check reruns long-chunk claims

A `lengthcheck` stage SHALL draw 300 claims from the `c2048` crossed answers with seed 20261119. It SHALL split each cited chunk into consecutive 512-token windows, keep the window that shares the most distinct lower-case claim words, and have GLM-5.3 and Clef-Flash judge the claim again against it. The report SHALL give the verdict change rate with a Wilson interval, as a registered sensitivity analysis with no gate.

#### Scenario: Window choice tie

- **WHEN** two windows share the same number of claim words
- **THEN** the stage MUST keep the earlier window

### Requirement: Closed-book runs check contamination

A `closedbook` stage SHALL answer every question once with no retrieval under two prompts: an own-knowledge prompt (the floor) and the main RAG answer prompt with an empty evidence block. It SHALL score both with `AnswerCorrectness` and the FinanceBench number match. Closed-book results SHALL be descriptive, with no hypothesis test.

#### Scenario: No search call

- **WHEN** either closed-book run runs
- **THEN** it MUST send no search call and MUST pass an empty evidence list

#### Scenario: RAG prompt with empty evidence

- **WHEN** the closed-book RAG-prompt run builds its prompt
- **THEN** the prompt MUST equal the main answer prompt with an empty evidence block, and its template hash MUST be recorded

### Requirement: A contamination sensitivity re-runs the correctness rows

The report SHALL show closed-book correctness per dataset beside every correctness table, and a per-question cross-table on retrieval misses (closed-book correct or not against RAG correct or not). A registered sensitivity analysis SHALL re-run rows 14, 15, 18 and 19 on the questions that both closed-book runs answer wrongly (Ragas correctness below 0.5).

#### Scenario: Contamination subset

- **WHEN** a question is answered correctly by one closed-book run and wrongly by the other
- **THEN** it MUST NOT enter the contamination subset

### Requirement: Missing answers and unjudged rows keep every question

The analysis SHALL keep every question in its dataset's denominator and SHALL count every exclusion per setup and row. An answer still missing when its run closes SHALL score 0 for correctness and number match and SHALL count as an answer with no factual claim. A Ragas or checker row still unjudged when its run closes SHALL leave that row's complete cases, SHALL be counted, and SHALL be scored 0 in a sensitivity analysis.

#### Scenario: Answer missing at run close

- **WHEN** an answer is still missing when its run closes
- **THEN** its correctness and number match MUST be 0 and it MUST count as an answer with no factual claim

### Requirement: Faithfulness uses complete cases with registered bounds

Faithfulness per question and setup SHALL be the mean over the runs with at least one factual claim. A question SHALL enter a faithfulness row only when every cell the row uses has a value. Two sensitivity analyses SHALL keep every question, with no-claim answers scored 1 and scored 0. The refusal rate per setup SHALL be reported as a co-outcome.

#### Scenario: Answer with no factual claim

- **WHEN** a question's answers in one cell of a faithfulness row have no factual claim in any run
- **THEN** the question MUST leave that row's complete cases, the exclusion MUST be counted, and both sensitivity analyses MUST include it

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
