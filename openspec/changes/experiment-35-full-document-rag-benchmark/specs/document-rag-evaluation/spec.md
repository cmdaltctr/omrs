# document-rag-evaluation Specification

## ADDED Requirements

### Requirement: Document benchmark uses full frozen public datasets

Experiment 35 SHALL evaluate OMRS on all 150 questions of the FinanceBench open sample, using the source PDFs, and on the 707 questions of the BioASQ `enelpol/rag-mini-bioasq` test split. Question IDs, source file hashes, gold labels and query order SHALL be frozen before the first measured run.

#### Scenario: A run starts from pre-extracted benchmark text
- **WHEN** a FinanceBench run bypasses the source PDF
- **THEN** it SHALL NOT count as the primary result
- **AND** it MAY be reported only as a diagnostic run

#### Scenario: The question set changes after scoring starts
- **WHEN** a question or source file is added, removed or replaced
- **THEN** the run SHALL use a new benchmark revision recorded as a plan amendment

### Requirement: BioASQ subset and fallback are decided before scoring

If BioASQ does not fit the time budget, the protocol SHALL either move it to other hardware or use every gold passage plus a seeded random sample of the other abstracts, frozen and reported before scoring. NFCorpus SHALL replace BioASQ only when BioASQ cannot be used, SHALL report retrieval metrics only, and SHALL be used only after its academic-use terms are checked.

#### Scenario: The fallback is used without a terms check
- **WHEN** NFCorpus runs and the protocol records no check of its academic-use terms
- **THEN** its results SHALL NOT enter the report

### Requirement: Arms change one component against one baseline

The baseline SHALL be the `documents` profile defaults with local Qwen3-Embedding-4B. Each ablation arm SHALL change one component: embedding 0.6B, embedding 8B, reranker off, token-aware chunking off, or hybrid search. All arms SHALL run on the same questions of each dataset.

#### Scenario: An arm changes two settings
- **WHEN** an arm differs from the baseline in more than one component
- **THEN** it SHALL NOT be reported as an ablation of either component

#### Scenario: The chunking arm changes no chunk
- **WHEN** token-aware chunking off gives the same chunks as the baseline on a dataset
- **THEN** that cell SHALL be reported as not applicable and SHALL NOT be run

### Requirement: Document retrieval metrics remain primary

The primary result SHALL report Recall@10, MRR@10 and nDCG@10 from gold labels, and hit@page for FinanceBench. nDCG@10 SHALL be the primary endpoint of the arm comparisons. Judge-based scores SHALL NOT replace these metrics.

#### Scenario: Ragas answer scores improve while retrieval degrades
- **WHEN** a secondary Ragas score improves but a primary metric worsens
- **THEN** the report SHALL present both outcomes
- **AND** it SHALL NOT hide the retrieval regression behind the secondary score

### Requirement: FinanceBench hits are scored at the gold page

A FinanceBench hit SHALL be a retrieved chunk from the gold document and the gold page. One frozen, tested function SHALL convert the zero-indexed `evidence_page_num` to stored page numbers. A chunk spanning pages SHALL hit when any of its pages is the gold page.

#### Scenario: A chunk comes from the gold page
- **WHEN** a retrieved chunk comes from the gold document and its page equals the converted gold page
- **THEN** the chunk SHALL count as a hit

#### Scenario: The page index is not converted
- **WHEN** the harness compares zero-indexed `evidence_page_num` values with stored page numbers without the frozen conversion
- **THEN** the page-index unit test SHALL fail before any measured run

### Requirement: Document failures are attributable by stage

The harness SHALL distinguish source evidence recovery, chunk preservation, retrieval and reranking, and answer-stage failures.

#### Scenario: Gold evidence is absent after parsing
- **WHEN** the gold evidence is not present in the extracted representation
- **THEN** the failure SHALL be attributed before retrieval
- **AND** the report SHALL NOT describe it as a ranking failure

### Requirement: Document evaluation does not change production defaults

The measured runs SHALL use the frozen profile settings of each arm. A finding that suggests a production default change SHALL go to a separate proposal.

#### Scenario: A setting is changed to improve a measured score
- **WHEN** a setting outside the arm definition changes after measured scoring starts
- **THEN** the run SHALL be labelled exploratory
- **AND** it SHALL NOT replace the frozen result
