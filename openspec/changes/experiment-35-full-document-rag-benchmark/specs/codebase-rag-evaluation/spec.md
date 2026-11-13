# codebase-rag-evaluation Specification

## ADDED Requirements

### Requirement: Software retrieval is measured on the FreshStack LangChain slice

Experiment 35 SHALL measure software retrieval on the 203 public FreshStack queries of the frozen LangChain slice (`prepare_freshstack.py`, seed 20260530). The 20 continuity queries from Experiment 9 SHALL NOT be scored (pre-freeze amendment A1, 2026-11-12). It SHALL build its own 9 indexes and SHALL run the same 72 search setups as the document benchmark. FreshStack nuggets MAY serve as the reference for Ragas context recall.

#### Scenario: An existing index is reused
- **WHEN** a run scores against an index built by an earlier experiment
- **THEN** it SHALL NOT count as an Experiment 35 result

#### Scenario: The query set is reduced
- **WHEN** a run scores fewer than the 203 frozen queries without a plan amendment
- **THEN** it SHALL NOT count as the measured result

#### Scenario: Continuity documents in the corpus
- **WHEN** the FreshStack corpus is loaded
- **THEN** it SHALL hold neither the 15 Experiment 9 continuity documents nor the overlay runbook

#### Scenario: A continuity query is scored
- **WHEN** a FreshStack run includes one of the 20 Experiment 9 continuity queries
- **THEN** that query SHALL NOT enter any Experiment 35 figure

### Requirement: Retrieved chunks count once per parent document

Each retrieved chunk SHALL be mapped to its parent document, and only the first rank of each parent SHALL count. The mapping SHALL reuse the code of Experiment 22's `run_eval.py`.

#### Scenario: Several chunks from one document are retrieved
- **WHEN** three chunks of the same parent document appear in the top 100 retrieved chunks
- **THEN** Recall@10 SHALL count that parent once, at the rank of its first chunk, and the 10-unit cut SHALL come after this collapse (amendment A2, 2026-11-13)

### Requirement: An earlier FreshStack run is reported only as a reference

Experiment 22 MAY be reported beside the result as a reference. The report SHALL label it a reference and SHALL list the settings that differ. Experiment 9a SHALL NOT be compared, because it used one vector per parent document.

#### Scenario: An earlier run is reported as a reference
- **WHEN** the report shows Experiment 22 beside the Experiment 35 FreshStack result
- **THEN** it SHALL label Experiment 22 as a reference, not the baseline
- **AND** it SHALL list the settings that differ, such as top_k, chunking and embedding model

### Requirement: Code answer benchmarks without retrieval labels are out of scope

Experiment 35 SHALL NOT score RepoProbe or any other code benchmark that gives no gold files or chunks. Such answer scoring needs an LLM judge for every score and SHALL go to a later paper.

#### Scenario: Retrieval metrics are requested for RepoProbe
- **WHEN** the harness is asked for Recall@K on a RepoProbe question
- **THEN** it SHALL report the metric as not measurable for that benchmark
- **AND** no RepoProbe score SHALL enter the Experiment 35 report
