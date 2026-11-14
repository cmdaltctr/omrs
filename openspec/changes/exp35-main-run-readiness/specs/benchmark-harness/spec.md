## ADDED Requirements

### Requirement: Hosted calls run under a per-provider concurrency limit

The harness SHALL limit the number of hosted calls in flight for each role: answers, the hosted claim judge and the Ragas judge. Each limit SHALL be a command-line setting with a frozen default. The run record and the stage trace SHALL hold the value that each role used, also when the default applied. A local claim judge SHALL have one call in flight at a time.

#### Scenario: Default value recorded

- **WHEN** an answer stage starts without a concurrency option
- **THEN** the run record and the trace settings MUST name the frozen default answer concurrency

#### Scenario: Limit never exceeded

- **WHEN** the answer concurrency is 4 and 20 questions wait
- **THEN** no more than 4 answer calls MUST be in flight at any time

#### Scenario: Local judge stays serial

- **WHEN** a judge stage runs the `clef_flash` or `granite_guardian` judge with a hosted judge concurrency of 4
- **THEN** that local judge MUST have no more than one call in flight

#### Scenario: Limit of one

- **WHEN** every concurrency limit is 1
- **THEN** the stage MUST send its calls one at a time, in frozen question order

### Requirement: A rate-limit reply is retried and never saved

A hosted call that ends with HTTP 429, or with HTTP 402 that carries `Retry-After`, SHALL be sent again. An HTTP 402 without `Retry-After` means out of credit and SHALL follow the out-of-credit rule below. The harness SHALL wait the `Retry-After` time when the error carries one, else a bounded exponential backoff with random jitter. A rate-limit error SHALL NOT be written as an answer, a verdict or a score.

#### Scenario: Retry-After honoured

- **WHEN** a judge call fails with HTTP 429 and `Retry-After: 7`
- **THEN** the harness MUST wait at least 7 seconds before it sends the call again, and the saved row MUST hold the later result

#### Scenario: Rate limit without a header

- **WHEN** an OpenRouter call fails with HTTP 429 and no `Retry-After` header
- **THEN** the harness MUST wait a backoff time and send the call again

#### Scenario: Spend limit with a header

- **WHEN** an OpenRouter call fails with HTTP 402 and `Retry-After: 20`
- **THEN** the harness MUST wait at least 20 seconds and send the call again

#### Scenario: Rate limit inside an answer result

- **WHEN** the answer call returns an error result that carries the OMRS `rate_limited` record
- **THEN** the harness MUST treat it as a rate limit, MUST use its `retry_after_seconds` as the `Retry-After` time, and MUST NOT write an answer row for that question
- **AND** the harness MUST NOT read the error text to find a rate limit

#### Scenario: Out of credit stops at once

- **WHEN** a hosted call fails with HTTP 402 and no `Retry-After`, or an answer result carries `rate_limited` with `kind` `out_of_credit`
- **THEN** the harness MUST NOT send the call again, MUST save no row for it, and MUST stop the stage with the rate-limit exit code and a message to top up the provider account

#### Scenario: Other errors unchanged

- **WHEN** an answer call fails with an error that is not a rate limit
- **THEN** the harness MUST keep the row with the error, as before this change

### Requirement: Repeated rate limits stop the stage cleanly

After a bounded number of rate-limit attempts for one item, the stage SHALL stop sending new calls. It SHALL keep every result that finishes, write no done-marker and exit with an exit code that names the rate limit. A later `--resume` SHALL send only the items that have no saved result.

#### Scenario: Attempts used up

- **WHEN** one question meets a rate limit on every attempt
- **THEN** the process MUST exit with the rate-limit exit code, and the stage MUST have no done-marker

#### Scenario: Resume after the stop

- **WHEN** the operator runs the same command with `--resume` after a rate-limit stop
- **THEN** the stage MUST send calls only for the items without a saved result

#### Scenario: Rate-limited question is not skipped

- **WHEN** a question met a rate limit on every attempt in an earlier process
- **THEN** `--resume` MUST send that question again, because no row was saved for it

### Requirement: Hybrid-on setups pin the BM25 sparse backend

The harness SHALL write `retrieval.hybrid_sparse_backend: bm25` into the scratch settings of every hybrid-on setup's process, as the protocol defines hybrid search as BM25 plus dense. It SHALL check the resolved value before the first query and SHALL record it in the trace settings.

#### Scenario: Pinned value recorded

- **WHEN** a hybrid-on setup's stage starts
- **THEN** its scratch settings MUST hold `retrieval.hybrid_sparse_backend: bm25`, and the trace settings MUST name `bm25`

#### Scenario: Environment overrides the pin

- **WHEN** the process environment sets `RETRIEVAL__HYBRID_SPARSE_BACKEND=native`
- **THEN** the hybrid-on stage MUST stop with a setup error before any query and MUST name the setting

### Requirement: Setups are named and configured by their settings

The harness SHALL build setups from four factors (embedder, chunk size, reranker, hybrid), named `e<embedder>-c<chunk size>-r<reranker>-h<hybrid>`, each searching index `e<embedder>-c<chunk size>`. It SHALL write the chunk size into `chunking.chunk_size` and `chunking.markdown_chunk_size`, 15% of it into `chunking.chunk_overlap`, and for reranker-on setups `retrieval.rerank_backend: llamacpp` and the reranker model. It SHALL refuse overrides and record the values.

#### Scenario: Settings of one setup

- **WHEN** the setup `e8b-c2048-r4b-hon` starts a search stage
- **THEN** its scratch settings MUST hold chunk size 2048, Markdown chunk size 2048, overlap 307, rerank backend `llamacpp`, the 4B reranker model and sparse backend `bm25`

#### Scenario: Chunk size overridden by the environment

- **WHEN** the process environment sets `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **THEN** the stage MUST stop with a setup error before ingest or any query, and MUST name the setting

#### Scenario: Embedder and reranker stay loaded together

- **WHEN** a reranker-on search stage runs
- **THEN** the router MUST list the embedder and the reranker and allow both loaded at once, so no query swaps a model

#### Scenario: Reranker falls back

- **WHEN** a query of a reranker-on search stage returns results with `_reranked` false or a `last_failure_reason`
- **THEN** the stage MUST save no row for that query, MUST stop with a setup error that names the query and the reason, and MUST write no done-marker
- **AND** `--resume` MUST send that query again

#### Scenario: Answer retrieval reranker falls back

- **WHEN** the retrieval of a reranker-on answer setup returns a result with `_reranked` false
- **THEN** the stage MUST stop with a setup error that names the question and the reason, and MUST write no answer from the un-reranked rows

### Requirement: The answer setups come from a fixed selection rule

A selection step SHALL read the saved half-A search scores of FinanceBench, FreshStack and BioASQ only (amendment A3). It SHALL choose the embedder size, then the reranker size: the smallest size whose pooled nDCG@10 (mean of the three dataset means) is within 0.01 of the best, inclusive; equal scores go to the smaller size. It SHALL write every pooled score and each choice. The answer stage SHALL refuse to start without that file.

#### Scenario: Legal scores do not change the choice

- **WHEN** only the Legal RAG Bench scores change between two selection runs
- **THEN** both runs MUST choose the same embedder size, reranker size and cell

#### Scenario: Selection reads half A only

- **WHEN** a planted effect exists only in the half-B questions (seed 20261115 split)
- **THEN** the selection MUST be the same as without that effect

#### Scenario: Gap of exactly 0.01

- **WHEN** the 0.6B reranker pools 0.010 below the best reranker size
- **THEN** the selection MUST choose 0.6B

#### Scenario: Search setup missing

- **WHEN** a search setup of any core dataset has no scores
- **THEN** the selection step MUST stop and name the setup

### Requirement: The selection step picks one cell for Part 2

At the chosen embedder and reranker size, the selection step SHALL pick chunk size, reranker on or off and hybrid on or off from the 12 cells by the same three-dataset pooled half-A score. Cells within 0.01 of the best, inclusive, SHALL tie. Ties SHALL go to reranker off, then hybrid off, then the chunk size with the lowest index cost, then the smaller chunk size (amendment A3). Index cost SHALL be chunks times embedding dimension over the three core datasets (A4).

#### Scenario: Four-factor tie

- **WHEN** the best cell has reranker on and hybrid on, and a cell with reranker off and hybrid on pools 0.008 lower
- **THEN** the selection MUST choose the cell with reranker off

#### Scenario: Index cost decides a chunk-size tie

- **WHEN** two tied cells differ only in chunk size and the 512-token indexes store more vector values than the 1,024-token indexes
- **THEN** the selection MUST choose the 1,024-token cell

### Requirement: The selection file holds a configuration hash

The selection step SHALL write the cell scores, the chosen cell and the configuration hash: the SHA-256 of the canonical JSON (keys sorted, no spaces, UTF-8) of the selected cell's resolved settings, with the SHA-256 of `halves.json` as one field. A sensitivity step SHALL repeat the cell choice with any-page nDCG@10 on FinanceBench and SHALL record whether the cell changes; the registered cell SHALL NOT change.

#### Scenario: Same hash twice

- **WHEN** the selection runs twice on the same scores and the same `halves.json`
- **THEN** both selection files MUST hold the same configuration hash

### Requirement: Half B is scored only after the hash is time-stamped

The harness SHALL follow pre-registration section 14.2: score half A; write the selection file; time-stamp its configuration hash by an OSF upload; then score half B and start the replicate pods. A scoring step SHALL refuse any half-B score unless the selection file exists and a time-stamp record holds its current configuration hash. A replicate pod's first stage SHALL refuse to start under the same condition.

#### Scenario: Half-B score before the time-stamp

- **WHEN** the scoring step is asked for half-B scores and no time-stamp record exists
- **THEN** it MUST stop before it computes any half-B score and MUST name the missing record

#### Scenario: Time-stamp of an earlier selection

- **WHEN** the scoring step is asked for half-B scores and the time-stamp record holds a hash that differs from the configuration hash in the selection file
- **THEN** it MUST stop before it computes any half-B score and MUST name both hashes

#### Scenario: Half-A scoring

- **WHEN** the scoring step is asked for half-A scores and no selection file exists
- **THEN** it MUST compute them

### Requirement: Halves keep FinanceBench documents apart

A split step SHALL write `halves.json` with seed 20261115. It SHALL split FinanceBench by document: documents are shuffled with the seed and each goes, with all its questions, to the half that has fewer questions so far, ties to half A. It SHALL split FreshStack, BioASQ and Legal RAG Bench by question: questions are shuffled with the seed and the first half, rounded up, is half A.

#### Scenario: No FinanceBench document in both halves

- **WHEN** the split runs on FinanceBench
- **THEN** every document's questions MUST sit in one half only

#### Scenario: Same halves twice

- **WHEN** the split runs twice with the same seed
- **THEN** both `halves.json` files MUST be byte-identical

### Requirement: Planned contrasts use one clustered method

The analysis SHALL compute rows 1 to 19 of pre-registration section 8 from per-question contrast scores. On FreshStack, BioASQ and Legal RAG Bench it SHALL use the closed-form test of pre-registration section 9 point 3 (mean, bias-reduced variance, t on n minus 1), computed through GEE and checked against the closed form. On FinanceBench it SHALL use a document-level sign-flip permutation test (100,000 draws, seed 20261101). It SHALL NOT fit a mixed model or use a McNemar or equivalence test.

#### Scenario: GEE matches the closed form

- **WHEN** the analysis runs on a fixed known-answer fixture of n contrast scores
- **THEN** the estimate MUST equal their mean, and the variance MUST equal the sum of squared residuals times (n / (n minus 1)) squared, divided by n squared
- **AND** the p-value and 95% interval MUST use t on n minus 1 degrees of freedom, whatever reference the library reports by default
- **AND** if the `statsmodels` GEE output differs from the closed form, the analysis MUST use the closed form and record the difference

#### Scenario: FinanceBench document clusters

- **WHEN** two FinanceBench questions share a document
- **THEN** the sign-flip test MUST flip their contrast scores together, as one document sum, and the 95% interval MUST come from inverting the same test on the same draws

#### Scenario: Type I error under the null

- **WHEN** the analysis runs on 200 simulated datasets with no planted effect and unequal error variance across cells
- **THEN** the share of rejections at 0.05 MUST stay near 0.05 for the GEE and for the sign-flip test

#### Scenario: Sensitivity check disagrees

- **WHEN** the paired permutation test by question on FreshStack disagrees with the GEE on whether a row counts
- **THEN** the decision MUST follow the GEE, and the row MUST appear in the disagreement table

### Requirement: Holm families are fixed before the run

The analysis SHALL apply Holm within each dataset over families fixed at 19 rows (FinanceBench), 19 (FreshStack) and 8 (BioASQ, rows 1 to 8). BioASQ rows 9 to 19 SHALL be sanity checks with unadjusted intervals. Legal RAG Bench SHALL have no family. A row that fails a gate SHALL stay in its family with p = 1 and SHALL be reported "not testable".

#### Scenario: Gated row keeps the family size

- **WHEN** rows 12, 13, 16 and 17 are "not testable" on FreshStack
- **THEN** Holm MUST still run over 19 rows on FreshStack, with those rows at p = 1

### Requirement: The answer stage has a token-matched setup for each chunk size

The answer stage SHALL run 15 setups: the 12 crossed setups on 10 chunks each and three token-matched setups (`c512-t20k`, `c1024-t20k` and `c2048-t20k`) at the chosen embedder and reranker size with reranker on and hybrid on. A token-matched setup SHALL cut its evidence at a hard limit of 20,480 real Qwen3 tokens. The chunk that crosses the limit SHALL be truncated at the limit, and the truncation SHALL be recorded per question. The `c2048` x 10 factorial cell SHALL keep its 10-chunk evidence.

#### Scenario: Setup table

- **WHEN** the answer setup table is built
- **THEN** it MUST hold 15 setups, and the three `-t20k` setups MUST use the token cut

#### Scenario: Factorial cell unchanged

- **WHEN** the chosen embedder and reranker retrieve short 2,048-token chunks
- **THEN** `c2048` x 10 MUST send exactly 10 chunks, and `c2048-t20k` MUST send chunks until the 20,480-token limit, truncating the chunk that crosses it and recording the truncation

### Requirement: FreshStack uses the full public corpus at a pinned revision

The FreshStack loader SHALL load the full public `freshstack/corpus-oct-2024` corpus, config `langchain`, at the revision pinned in `plan.json`, and the 203 public queries. It SHALL refuse a corpus whose revision or row count differs from the pin. It SHALL NOT sample a subset, add distractors, load the 20 continuity queries or the continuity documents, or append the overlay runbook.

#### Scenario: Subset on disk

- **WHEN** the corpus folder holds the 10,000-document subset of Experiments 9a and 22
- **THEN** the loader MUST stop before any ingest and MUST name the expected and the found row counts

### Requirement: Evidence recall gives any-page credit on FinanceBench

`evidence_recall_20k` SHALL be the share of a question's gold units covered by the evidence that the token cut takes from the top 100 chunks. On FinanceBench a whole chunk SHALL cover every gold page it overlaps, and the truncated crossing chunk only its first page; first-page credit SHALL be a sensitivity column. Elsewhere a chunk SHALL cover its one unit. nDCG@10, Recall@10, MRR@10 and hit@page SHALL keep first-page credit as primary.

#### Scenario: Chunk across two pages

- **WHEN** a whole FinanceBench chunk spans pages 41 and 42 and the gold page is 42
- **THEN** `evidence_recall_20k` MUST count page 42 as covered, and the first-page column MUST NOT

#### Scenario: Truncated chunk across two pages

- **WHEN** the crossing chunk spans pages 41 and 42, is truncated, and the gold page is 42
- **THEN** `evidence_recall_20k` MUST NOT count page 42 as covered by that chunk

### Requirement: Parallel and serial runs write the same row files

A stage SHALL write its row file and its trace rows in frozen question order, whatever order the calls finish in. With a fixed clock and deterministic call results (stub calls), a run at any concurrency SHALL give a row file with the same bytes as a run at concurrency 1. Its trace file SHALL be the same after the concurrency values in the trace settings are removed; the trace keeps the value each role used.

#### Scenario: Calls finish out of order

- **WHEN** the call for question 3 finishes before the calls for questions 1 and 2
- **THEN** the row file MUST hold the rows of questions 1, 2 and 3 in that order

#### Scenario: Same bytes as serial

- **WHEN** one stage runs on stub calls with a fixed clock, once at concurrency 8 and once at concurrency 1
- **THEN** the two row files MUST be byte-identical, and the two trace files MUST be byte-identical after the concurrency values are removed from their trace settings
- **AND** each trace MUST still record the concurrency value of its own run

#### Scenario: Live hosted calls

- **WHEN** a stage runs on live hosted calls at two concurrency values
- **THEN** row content MAY differ, and the row order and keys MUST still match

### Requirement: A finished result survives a stop

A result that finishes before an earlier item SHALL be kept on disk at once. A stop SHALL NOT lose it, and `--resume` SHALL write it in its place in the frozen order without a new call.

#### Scenario: Stop with a result held back

- **WHEN** question 3 has finished, question 2 is still in flight, and the stage stops
- **THEN** `--resume` MUST write the row of question 3 from disk without a new call for question 3

#### Scenario: Stop after a paid call returns and before its result is saved

- **WHEN** a worker's paid call for question 4 returns, the pod stops before the result reaches the pending file, and `--resume` runs
- **THEN** a dispatch record for question 4 MUST have been flushed and fsynced before the call, and `--resume` MUST send the call for question 4 again, because that record exists and no row and no pending result exist for it
- **AND** it MUST send at most one such call per worker for that stop, and MUST NOT choose to send again from the content of any answer
- **AND** the stage trace MUST count each resent call in `resent_calls`
