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

### Requirement: Hypotheses are pre-registered with numbered rows and fixed Holm families

The protocol SHALL register H1 to H7, H8a and H8b before the run, each within scope S, with the rows, endpoints, null and holds rule of `preregistration.md` sections 7 and 8. Every null SHALL be a zero effect. H8a (12 crossed setups) and H8b (3 token-matched setups) SHALL both be confirmatory. Legal RAG Bench SHALL stay exploratory in every hypothesis, H8a and H8b correctness included.

#### Scenario: A row counts
- **WHEN** a directional row has a Holm-adjusted p below 0.05 and an estimate with the predicted sign, or a two-sided row has a Holm-adjusted p below 0.05
- **THEN** the row SHALL count on that dataset

#### Scenario: A hypothesis holds
- **WHEN** the rows of H1 to H5 count on at least 2 of 3 core datasets by the hypothesis's rule, or the rows of H6, H7, H8a or H8b count on both FinanceBench and FreshStack by the hypothesis's rule
- **THEN** the hypothesis SHALL hold

#### Scenario: A two-sided row counts with opposite signs
- **WHEN** row 9 counts on FinanceBench with a positive estimate and on FreshStack with a negative estimate
- **THEN** the report SHALL state the row as a dataset-dependent effect with both directions, and H6 SHALL NOT hold on that row

#### Scenario: Direction opposite to the hypothesis
- **WHEN** a directional row is significant but its sign is opposite to the stated direction
- **THEN** the report SHALL say the row does not count, and SHALL report the opposite effect as a finding

#### Scenario: Chunk-size rows on BioASQ
- **WHEN** rows 9 to 19 are computed on BioASQ
- **THEN** they SHALL be reported as sanity checks with unadjusted 95% intervals and SHALL NOT count for or against H6, H7, H8a or H8b, which are tested on FinanceBench and FreshStack

#### Scenario: Legal result
- **WHEN** a contrast counts on Legal RAG Bench
- **THEN** it SHALL NOT count towards any hypothesis

#### Scenario: H8a holds and H8b does not
- **WHEN** H8a holds for an outcome and H8b does not
- **THEN** the report SHALL claim only that chunk size together with context length changes that outcome

#### Scenario: FinanceBench interval
- **WHEN** a decision p-value or 95% interval is computed on FinanceBench
- **THEN** it SHALL come from the document-level sign-flip permutation test, so questions that share a document move together

### Requirement: Retrieval is scored on distinct units after collapse

Each search setup SHALL save its top 100 chunks, with a rerank pool of exactly 100. The scorer SHALL collapse chunks to units (FreshStack document, FinanceBench page, BioASQ or Legal passage) in rank order, keep the first occurrence of each unit and cut at 10 units. `evidence_recall_20k` SHALL take chunks in rank order up to 20,480 real Qwen3 tokens and truncate the chunk that crosses the limit.

#### Scenario: Big chunks gain nothing by construction
- **WHEN** two setups give the same unit order but one uses 2,048-token chunks
- **THEN** both SHALL score the same nDCG@10

#### Scenario: Spanning page in nDCG@10
- **WHEN** a FinanceBench chunk spans pages 41 and 42 and the gold page is 42
- **THEN** for nDCG@10, Recall@10, MRR@10 and hit@page the chunk SHALL count for page 41, and any-page credit SHALL appear only in the sensitivity column

#### Scenario: Spanning page in evidence_recall_20k
- **WHEN** a whole chunk inside the 20,480-token evidence spans pages 41 and 42 and the gold page is 42
- **THEN** `evidence_recall_20k` SHALL count gold page 42 as covered (any-page credit), and first-page credit SHALL appear only in the sensitivity column

#### Scenario: Truncated crossing chunk
- **WHEN** the chunk that crosses 20,480 tokens spans pages 7 and 8 and is truncated
- **THEN** it SHALL cover only page 7, because the reader stores no page offsets inside a chunk

### Requirement: The answer stage uses the selection rule fixed before the run

On half A only, the harness SHALL choose the smallest embedder, then the smallest reranker size, within 0.01 of the best pooled nDCG@10 over FinanceBench, FreshStack and BioASQ; Legal RAG Bench SHALL take no part. The answer stage SHALL run 15 setups (12 crossed, 3 token-matched), 3 runs each, plus two closed-book runs and one oracle run. H8a and H8b SHALL use all questions.

#### Scenario: Two sizes within the margin
- **WHEN** the 4B embedder pools 0.612 and the 8B embedder pools 0.619
- **THEN** the rule SHALL choose 4B

#### Scenario: Legal excluded from the pool
- **WHEN** the harness pools the per-dataset nDCG@10 means for a size
- **THEN** it SHALL average the FinanceBench, FreshStack and BioASQ means and SHALL NOT include the Legal RAG Bench mean

### Requirement: Halves are fixed before any score

Each dataset SHALL be split into half A and half B with seed 20261115. FinanceBench SHALL be split by document, so no document sits in both halves; FreshStack, BioASQ and Legal RAG Bench SHALL be split by question. Every selection step, and every pre-freeze sample drawn after `halves.json` exists, SHALL read half A only. Samples drawn earlier (smoke runs, test pod, classifier-gate claims) SHALL be listed with their question IDs and, once `halves.json` exists, their half.

#### Scenario: FinanceBench document in both halves
- **WHEN** `halves.json` puts two questions of one FinanceBench document in different halves
- **THEN** the split SHALL fail its check before any score is computed

#### Scenario: A pre-freeze sample reaches half B
- **WHEN** the MDE pilot or a RAGFlow pre-freeze check, drawn after `halves.json` exists, draws a half-B question
- **THEN** that sample SHALL NOT be used

#### Scenario: A sample drawn before the halves
- **WHEN** a smoke-run, test-pod or classifier-gate sample was drawn before `halves.json` existed
- **THEN** it SHALL be listed with its question IDs and their halves, and SHALL NOT be scored as a result

### Requirement: Half A also fixes the OMRS setup for the RQ1 headline and Part 2

At the chosen embedder and reranker size, the harness SHALL pick chunk size, reranker on or off and hybrid on or off by pooled half-A mean nDCG@10. Cells within 0.01 of the best SHALL tie, resolved in order: reranker off, hybrid off, lowest index cost, smaller chunk size. The order SHALL be: score half A, write `selection.json`, time-stamp the configuration hash on OSF, then score half B.

#### Scenario: Tie goes to the cheaper cell
- **WHEN** the best cell has the reranker on and a cell with the reranker off scores 0.008 lower
- **THEN** the rule SHALL choose the cell with the reranker off

#### Scenario: Index cost decides a tie
- **WHEN** tied cells are compared on index cost
- **THEN** index cost SHALL be the stored vector values (chunks times embedding dimension) summed over the three core datasets, known from the sealed indexes before any score

#### Scenario: Configuration hash is written
- **WHEN** `selection.json` is written
- **THEN** it SHALL hold the pooled scores, both chosen sizes, the chosen cell and the configuration hash: the SHA-256 of the canonical JSON of the cell's resolved settings plus the `halves.json` SHA-256

#### Scenario: Half-B score before the time stamp
- **WHEN** a step asks for a half-B score
- **THEN** `selection.json` SHALL already exist, and the OSF time stamp of its hash SHALL already exist

#### Scenario: RQ1 headline
- **WHEN** the report gives the RQ1 retrieval headline
- **THEN** it SHALL be the chosen cell's nDCG@10 on half B with its 95% interval, and the 72-setup table on all questions SHALL be labelled descriptive

### Requirement: Every answer is one synthesis round

Every answer setup SHALL use `answer.context_window` 131,072 characters and `answer.max_rounds` 1, so all evidence goes to the answer model in one call. The answer stage SHALL record, for every answer, the rounds, the evidence characters and any truncation. Before the freeze, a test SHALL show that the largest evidence set of each answer setup fits one round.

#### Scenario: Setup needs a second round
- **WHEN** the largest evidence set of any answer setup needs more than one round
- **THEN** the pre-freeze test SHALL fail and name the setup

#### Scenario: Evidence truncated
- **WHEN** OMRS cuts evidence to fit the round budget
- **THEN** the answer row SHALL record the truncation and the characters dropped, and the report SHALL count truncated answers per setup

### Requirement: Answer correctness is judged against reference answers and gated per dataset

The Ragas stage SHALL score every answer with Ragas 0.4.3 `AnswerCorrectness` against the reference answer, and the judge SHALL never see the retrieved contexts. L1 SHALL label 50 half-B questions per core dataset (seed 20261113), each with one answer from run 1 of an answer setup the seed picks uniformly at random, and 50 Legal RAG Bench answers drawn the same way and reported without a gate.

#### Scenario: Gate passes on a dataset
- **WHEN** Cohen's kappa between the score cut at 0.5 and the human label has a point estimate of at least 0.60 and a lower 95% bound of at least 0.40, with "can't tell" items scored both ways, and the AUC of the continuous score has a lower 95% bound above 0.5
- **THEN** rows 14, 15, 18 and 19 SHALL be testable on that dataset

#### Scenario: Low agreement on one dataset
- **WHEN** the correctness gate fails on FreshStack
- **THEN** rows 14, 15, 18 and 19 SHALL be reported as not testable on FreshStack, staying in its Holm family with p = 1
- **AND** the other datasets SHALL keep their rows

### Requirement: FinanceBench answers get a number-match check

A tested, deterministic function SHALL compare the numbers of each FinanceBench reference answer with the generated answer after unit normalisation (thousands, millions, billions, currency and percent signs, parentheses for negatives). A question SHALL pass when every reference number appears in the answer, equal after rounding to the reference's decimal places or within 1% relative difference. The result SHALL be a secondary correctness outcome.

#### Scenario: Units differ
- **WHEN** the reference says "$1,577 million" and the answer says "$1.58 billion"
- **THEN** the check SHALL pass

#### Scenario: Number missing
- **WHEN** the answer gives no number that matches the reference figure
- **THEN** the check SHALL fail for that question

### Requirement: Document retrieval metrics remain primary

nDCG@10 on distinct units SHALL be the primary metric of the study. `evidence_recall_20k` SHALL be the confirmatory endpoint for H6 and H7 on FinanceBench (rows 9 to 11). Recall@10, MRR@10, hit@page (FinanceBench) and alpha-nDCG@10 (FreshStack, when its nugget labels allow) SHALL be secondary retrieval metrics. Scoring SHALL count documents, pages or passages, never chunks. Judge-based scores SHALL NOT replace these metrics.

#### Scenario: Ragas answer scores improve while retrieval degrades
- **WHEN** a secondary Ragas score improves but the primary metric worsens
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

### Requirement: Closed-book runs bound contamination

Two closed-book runs SHALL answer every question once without evidence: one with an own-knowledge prompt, and one with the main answer prompt and an empty evidence block. Both SHALL be descriptive single runs.

#### Scenario: Correct without retrieval
- **WHEN** a RAG answer is correct although its evidence holds no gold unit
- **THEN** the per-dataset cross-table SHALL show whether the closed-book answers were also correct

#### Scenario: Contamination subset
- **WHEN** the H8a and H8b correctness rows 14, 15, 18 and 19 are reported
- **THEN** the report SHALL also give them, marked as a registered sensitivity analysis, on the questions both closed-book runs answer wrongly (Ragas correctness below 0.5)

### Requirement: Missing outcomes keep every question in the denominator

Every question SHALL stay in its dataset's denominator, and every exclusion SHALL be counted per setup and row, by the rules of `preregistration.md` section 12.

#### Scenario: Short search list
- **WHEN** a search list holds fewer than 10 units
- **THEN** the missing ranks SHALL score as not relevant

#### Scenario: Answer call fails after resend
- **WHEN** an answer is still missing when the run closes
- **THEN** it SHALL score 0 for correctness and number match and stay in the denominator
- **AND** the report SHALL count it

#### Scenario: Answer with no factual claim
- **WHEN** an answer holds no factual claim
- **THEN** faithfulness SHALL be undefined for that run, and the two registered bounds (scored 1, scored 0) SHALL be reported

#### Scenario: Row still unjudged
- **WHEN** a Ragas or checker row is still unjudged when the run closes
- **THEN** it SHALL leave that row's complete cases and be counted, and a sensitivity analysis SHALL score it 0
