# codebase-rag-evaluation Specification

## ADDED Requirements

### Requirement: Software retrieval is measured on the full FreshStack LangChain corpus

Experiment 35 SHALL measure software retrieval on the 203 public FreshStack queries (`freshstack/queries-oct-2024`, config `langchain`) against the full public LangChain corpus (`freshstack/corpus-oct-2024`, 49,514 documents) at a pinned revision (amendment A4, 2026-11-14). It SHALL build its own 9 indexes and run the same 72 search setups as the document benchmark. The 20 Experiment 9 continuity queries SHALL NOT be scored.

#### Scenario: An existing index is reused
- **WHEN** a run scores against an index built by an earlier experiment
- **THEN** it SHALL NOT count as an Experiment 35 result

#### Scenario: The query set is reduced
- **WHEN** a run scores fewer than the 203 frozen queries without a plan amendment
- **THEN** it SHALL NOT count as a measured result

#### Scenario: The corpus is a subset
- **WHEN** a FreshStack index holds fewer documents than the pinned full corpus, such as the retired 10,000-document subset of Experiments 9a and 22
- **THEN** its scores SHALL NOT count as Experiment 35 results

#### Scenario: Continuity documents in the corpus
- **WHEN** the FreshStack corpus is loaded
- **THEN** it SHALL hold neither the 15 Experiment 9 continuity documents nor the overlay runbook

#### Scenario: A continuity query is scored
- **WHEN** a FreshStack run includes one of the 20 Experiment 9 continuity queries
- **THEN** that query SHALL NOT enter any Experiment 35 figure

#### Scenario: Nugget labels
- **WHEN** the FreshStack nugget labels allow it
- **THEN** alpha-nDCG@10 SHALL be reported as a secondary metric with the benchmark's own scorer, else as not available
- **AND** the nuggets MAY serve as the reference for Ragas context recall

### Requirement: Retrieved chunks count once per parent document

Each retrieved chunk SHALL be mapped to its parent document, and only the first rank of each parent SHALL count. The mapping SHALL reuse the code of Experiment 22's `run_eval.py`.

#### Scenario: Several chunks from one document are retrieved
- **WHEN** three chunks of the same parent document appear in the top 100 retrieved chunks
- **THEN** Recall@10 SHALL count that parent once, at the rank of its first chunk, and the 10-unit cut SHALL come after this collapse (amendment A2, 2026-11-13)

### Requirement: An earlier FreshStack run is reported only as a reference

Experiment 22 MAY be reported beside the result as a reference. The report SHALL label it a reference, SHALL state that it used the retired 10,000-document subset, and SHALL list the settings that differ. Experiment 9a SHALL NOT be compared, because it used one vector per parent document. No FreshStack result SHALL be compared with the public leaderboard unless the same corpus and metric are used.

#### Scenario: An earlier run is reported as a reference
- **WHEN** the report shows Experiment 22 beside the Experiment 35 FreshStack result
- **THEN** it SHALL label Experiment 22 a reference, not a baseline
- **AND** it SHALL name the corpus difference and list the settings that differ, such as top_k, chunking and the embedding model

### Requirement: Code answer benchmarks without retrieval labels are out of scope

Experiment 35 SHALL NOT score RepoProbe or any other code benchmark that gives no gold files or chunks. Such answer scoring needs an LLM judge for every score and SHALL go to a later paper.

#### Scenario: Retrieval metrics are requested for RepoProbe
- **WHEN** the harness is asked for Recall@K on a RepoProbe question
- **THEN** it SHALL report the metric as not measurable for that benchmark
- **AND** no RepoProbe score SHALL enter the Experiment 35 report
