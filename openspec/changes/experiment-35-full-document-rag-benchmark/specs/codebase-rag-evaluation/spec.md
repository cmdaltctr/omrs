# codebase-rag-evaluation Specification

## ADDED Requirements

### Requirement: Software retrieval is measured on the FreshStack LangChain slice

Experiment 35 SHALL measure software retrieval on all 223 queries of the frozen FreshStack LangChain slice (`prepare_freshstack.py`, seed 20260530). It SHALL build a new index for each arm and SHALL run the same arms as the document benchmark, with the `documents` profile as the baseline.

#### Scenario: An existing index is reused as the baseline
- **WHEN** a run scores against an index built by an earlier experiment
- **THEN** it SHALL NOT count as an Experiment 35 result

#### Scenario: The query set is reduced
- **WHEN** a run scores fewer than the 223 frozen queries without a plan amendment
- **THEN** it SHALL NOT count as the measured result

### Requirement: Retrieved chunks count once per parent document

Each retrieved chunk SHALL be mapped to its parent document, and only the first rank of each parent SHALL count. The mapping SHALL reuse the code of Experiment 22's `run_eval.py`.

#### Scenario: Several chunks from one document are retrieved
- **WHEN** three chunks of the same parent document appear in the top 10
- **THEN** Recall@10 SHALL count that parent once, at the rank of its first chunk

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
