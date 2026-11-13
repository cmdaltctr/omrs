# document-rag-evaluation Specification

## ADDED Requirements

### Requirement: Document benchmark uses full frozen public datasets

Experiment 35 SHALL evaluate OMRS on the 150 FinanceBench questions (`PatronusAI/financebench`) from the source PDFs, the 707 BioASQ questions (`enelpol/rag-mini-bioasq`, test split) and the 100 Legal RAG Bench questions (`isaacus/legal-rag-bench`). Question IDs, file hashes, gold labels and query order SHALL be frozen before the first measured run. Legal RAG Bench results SHALL be labelled exploratory (low power).

#### Scenario: A run starts from pre-extracted benchmark text
- **WHEN** a FinanceBench run bypasses the source PDF
- **THEN** it SHALL NOT count as the primary result
- **AND** it MAY be reported only as a diagnostic run

#### Scenario: The question set changes after scoring starts
- **WHEN** a question or source file is added, removed or replaced
- **THEN** the run SHALL use a new benchmark revision recorded as a plan amendment

#### Scenario: Legal results in a table
- **WHEN** the report shows a Legal RAG Bench figure
- **THEN** the figure SHALL be labelled exploratory

### Requirement: BioASQ subset and fallback are decided before scoring

If BioASQ does not fit the time budget, the protocol SHALL either move it to other hardware or use every gold passage plus a seeded random sample of the other abstracts, frozen and reported before scoring. NFCorpus SHALL replace BioASQ only when BioASQ cannot be used, SHALL report retrieval metrics only, and SHALL be used only after its academic-use terms are checked.

#### Scenario: The fallback is used without a terms check
- **WHEN** NFCorpus runs and the protocol records no check of its academic-use terms
- **THEN** its results SHALL NOT enter the report

### Requirement: The search stage is a full factorial of four factors

The search stage SHALL run every combination of embedder (Qwen3-Embedding 0.6B, 4B, 8B), chunk size (512, 1,024, 2,048 tokens, 15% overlap), reranker (off, Qwen3-Reranker 0.6B, 4B, 8B) and hybrid (off, or BM25 plus dense with RRF) on every dataset: 9 indexes and 72 setups per dataset, on the same questions. A setup SHALL be named by its settings (`e<embedder>-c<chunk size>-r<reranker>-h<hybrid>`), never by a profile name.

#### Scenario: A setup appears in the outputs
- **WHEN** a trace, output folder or report table names a setup
- **THEN** it SHALL use the settings name, for example `e4b-c1024-r0.6b-hon`, and SHALL NOT use a profile name such as `documents-profile-4b`

#### Scenario: Token-aware chunking silently falls back
- **WHEN** a setup resolves to `legacy_fallback` because the tokenizer is unavailable for any reason (blank model or revision, not cached, or fails to load)
- **THEN** the run SHALL stop before embedding and name the tokenizer model and revision

#### Scenario: A combination is missing
- **WHEN** the search stage of a dataset finishes with fewer than 72 setups scored
- **THEN** the hypothesis tests of that dataset SHALL NOT start, and the report SHALL name the missing setups

### Requirement: One chunk size per level for every file type

For each chunk-size level, the harness SHALL set `chunking.chunk_size` and `chunking.markdown_chunk_size` to the level and `chunking.chunk_overlap` to 15% of it, in every process, and record them. Every dataset's text SHALL reach the Markdown splitter (BioASQ and Legal passages written as `.md`), so all chunks are counted with the pinned Qwen3 tokenizer.

#### Scenario: Markdown and plain text in one setup
- **WHEN** a 1,024-token setup ingests FinanceBench PDFs (read as Markdown) and BioASQ passages (written as `.md`)
- **THEN** both SHALL be split with a size of 1,024 and an overlap of 154, counted with the pinned Qwen3 tokenizer

#### Scenario: Environment overrides a chunk setting
- **WHEN** the process environment or `.env` sets `CHUNKING__CHUNK_SIZE` or `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **THEN** the stage SHALL stop with a setup error before ingest and name the setting

### Requirement: Search hypotheses are pre-registered with a paired test and Holm correction

The protocol SHALL register H1 to H8 before the run. Per dataset, a mixed model (`MixedLM`, random intercept per question) SHALL give estimates, and a GEE with cluster-robust errors SHALL give each contrast's p-value, Holm-corrected within the dataset. A contrast SHALL count when the adjusted p is below 0.05 and its sign matches. A hypothesis SHALL hold overall on at least 2 of FinanceBench, FreshStack and BioASQ; Legal SHALL stay exploratory.

#### Scenario: Direction opposite to the hypothesis
- **WHEN** a contrast is significant but its sign is opposite to the stated direction
- **THEN** the report SHALL say the hypothesis does not hold, and SHALL report the opposite effect as a finding

#### Scenario: H6 on short-document sets
- **WHEN** chunk-size contrasts are computed on BioASQ
- **THEN** they SHALL be reported as a sanity check and SHALL NOT count for or against H6, which is tested on FinanceBench (endpoint `evidence_recall_20k`) and FreshStack (nDCG@10) and holds only when both support it

#### Scenario: Legal result
- **WHEN** a contrast counts on Legal RAG Bench
- **THEN** it SHALL NOT count towards any hypothesis

#### Scenario: FinanceBench interval
- **WHEN** a bootstrap interval is computed on FinanceBench
- **THEN** whole documents SHALL be resampled

### Requirement: Retrieval is scored on distinct units after collapse

Each search setup SHALL save the top 100 chunks, with a rerank pool of exactly 100. The scorer SHALL collapse chunks to units (document, FinanceBench first page, passage) in rank order and cut at 10. Equal evidence SHALL be cut by the running total of real Qwen3 tokens up to 20,480.

#### Scenario: Big chunks gain nothing by construction
- **WHEN** two setups give the same unit order but one uses 2,048-token chunks
- **THEN** both SHALL score the same nDCG@10

#### Scenario: Spanning page
- **WHEN** a FinanceBench chunk spans pages 41 and 42 and the gold page is 42
- **THEN** the chunk SHALL count for page 41, and the "any page" credit SHALL appear only in a sensitivity column

### Requirement: The answer stage uses a selection rule fixed before the run

On half A (seed 20261115), the harness SHALL choose the smallest embedder, then reranker size, within 0.01 pooled nDCG@10 of the best (ties to the smaller). The pooled score SHALL be the mean over the three core datasets (FinanceBench, FreshStack, BioASQ); Legal RAG Bench SHALL take no part. The answer stage SHALL run 15 setups (12 crossed, 3 token-matched; A3), 3 runs each, plus closed-book and oracle runs. H8 SHALL use all questions; descriptive headlines half B.

#### Scenario: Two sizes within the margin
- **WHEN** the 4B embedder pools 0.612 and the 8B embedder pools 0.619
- **THEN** the rule SHALL choose 4B

#### Scenario: Legal excluded from the pool
- **WHEN** the harness pools the per-dataset nDCG@10 means for a size
- **THEN** it SHALL average the FinanceBench, FreshStack and BioASQ means and SHALL NOT include the Legal RAG Bench mean

#### Scenario: Selection recorded before answers
- **WHEN** a replicate pod starts an answer stage
- **THEN** `protocol.md` SHALL already hold a dated note with the pooled scores and the chosen sizes

### Requirement: Half A also fixes the OMRS setup for Part 2

At the chosen embedder and reranker size, the harness SHALL pick chunk size, reranker on or off and hybrid on or off by the pooled half-A mean nDCG@10 over the three core datasets. Cells within 0.01 of the best SHALL tie, and ties SHALL resolve in this order: reranker off, hybrid off, lowest index cost, smaller chunk size. The configuration hash of the chosen cell SHALL go to `protocol.md` before half B opens for Part 2.

#### Scenario: Tie goes to the cheaper cell
- **WHEN** the best cell has reranker on and a cell with reranker off scores 0.008 lower
- **THEN** the rule SHALL choose the cell with reranker off

#### Scenario: Hash recorded before half B opens
- **WHEN** Part 2 is about to read half B
- **THEN** `protocol.md` SHALL already hold a dated note with the cell scores, the chosen cell and its configuration hash

### Requirement: Every answer is one synthesis round

Every answer setup SHALL use `answer.context_window` 131,072 characters and `answer.max_rounds` 1, so all evidence goes to the answer model in one call. The answer stage SHALL record, for every answer, the rounds, the evidence characters and any truncation. Before the freeze, a test SHALL show that the largest evidence set of each answer setup fits one round.

#### Scenario: Setup needs a second round
- **WHEN** the largest evidence set of any answer setup needs more than one round
- **THEN** the pre-freeze test SHALL fail and name the setup

#### Scenario: Evidence truncated
- **WHEN** OMRS cuts evidence to fit the round budget
- **THEN** the answer row SHALL record the truncation and the characters dropped, and the report SHALL count truncated answers per setup

### Requirement: Answer correctness is judged against reference answers and validated by hand

The Ragas stage SHALL score every answer with Ragas 0.4.3 `AnswerCorrectness` against the reference answer. L1 SHALL label 100 main-run answers (25 per dataset) and 200 claims; L2 SHALL label 30% of each set. The report SHALL give kappa with intervals per dataset and checker, and L1 against L2. Below pooled kappa 0.60, correctness SHALL be exploratory.

#### Scenario: Low agreement
- **WHEN** the pooled kappa between the binarised Ragas score and the operator labels is 0.52
- **THEN** answer correctness SHALL be labelled exploratory, and H8 SHALL rest on faithfulness and the FinanceBench number match

### Requirement: FinanceBench answers get a number-match check

A tested, deterministic function SHALL compare the numbers of each FinanceBench reference answer with the generated answer after unit normalisation (thousands, millions, billions, currency and percent signs, parentheses for negatives). A question SHALL pass when every reference number appears in the answer, equal after rounding to the reference's decimal places or within 1% relative difference. The result SHALL be a secondary correctness outcome.

#### Scenario: Units differ
- **WHEN** the reference says "$1,577 million" and the answer says "$1.58 billion"
- **THEN** the check SHALL pass

#### Scenario: Number missing
- **WHEN** the answer gives no number that matches the reference figure
- **THEN** the check SHALL fail for that question

### Requirement: Document retrieval metrics remain primary

nDCG@10 on distinct units SHALL be the only primary metric. Recall@10, MRR@10 and hit@page (FinanceBench) SHALL be secondary retrieval metrics. Scoring SHALL count documents, pages or passages, never chunks. Judge-based scores SHALL NOT replace these metrics.

#### Scenario: Ragas answer scores improve while retrieval degrades
- **WHEN** a secondary Ragas score improves but a primary metric worsens
- **THEN** the report SHALL present both outcomes
- **AND** it SHALL NOT hide the retrieval regression behind the secondary score

### Requirement: FinanceBench hits are scored at the gold page

A FinanceBench hit SHALL be a retrieved unit on the gold document and the gold page. One frozen, tested function SHALL convert the zero-indexed `evidence_page_num` to stored page numbers. A chunk spanning pages SHALL count for its first page (amendment A2, 2026-11-13).

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

The measured runs SHALL use the frozen settings of each setup. A finding that suggests a production default change SHALL go to a separate proposal.

#### Scenario: A setting is changed to improve a measured score
- **WHEN** a setting outside the setup definition changes after measured scoring starts
- **THEN** the run SHALL be labelled exploratory
- **AND** it SHALL NOT replace the frozen result

### Requirement: An oracle run gives a descriptive ceiling

One oracle run SHALL answer every question with its gold units (capped at 20,480 Qwen3 tokens) and no retrieval, with the main answer prompt and settings, scored like the main runs. It SHALL be reported beside closed-book as single-run ceiling and floor, without a test, noting it has no distractors.

#### Scenario: FreshStack gold over budget
- **WHEN** a question's gold units (FreshStack, FinanceBench or BioASQ) exceed 20,480 Qwen3 tokens
- **THEN** the context SHALL be cut at that budget and the truncation SHALL be recorded for that question

### Requirement: The rerank pool stays 100 at depth 100

Every reranker setup SHALL pass `fetch_k` 100 so the rerank pool is 100 chunks when the harness asks for 100 results.

#### Scenario: Pool without the override
- **WHEN** a reranker search asks for 100 results without `fetch_k`
- **THEN** the pool would be 300, and the harness SHALL refuse that call shape

### Requirement: Closed-book misses are cross-tabulated

On questions where retrieval missed every gold unit, the report SHALL cross-tabulate closed-book correct or not against RAG correct or not, per dataset.

#### Scenario: Correct without retrieval
- **WHEN** a RAG answer is correct although its evidence holds no gold unit
- **THEN** the cross-table SHALL show whether the closed-book answer was also correct
