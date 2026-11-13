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

A hosted call that ends with HTTP 429 or HTTP 402 SHALL be sent again. The harness SHALL wait the `Retry-After` time when the error carries one, else a bounded exponential backoff with random jitter. A rate-limit error SHALL NOT be written as an answer, a verdict or a score.

#### Scenario: Retry-After honoured

- **WHEN** a judge call fails with HTTP 429 and `Retry-After: 7`
- **THEN** the harness MUST wait at least 7 seconds before it sends the call again, and the saved row MUST hold the later result

#### Scenario: Spend limit without a header

- **WHEN** an OpenRouter call fails with HTTP 402 and no `Retry-After` header
- **THEN** the harness MUST wait a backoff time and send the call again

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

### Requirement: The answer setups come from a fixed selection rule

A selection step SHALL read the saved search scores and SHALL choose the embedder size and then the reranker size: the smallest size whose pooled nDCG@10 (the plain mean of the per-dataset means) is within 0.01 of the best, inclusive, with equal scores going to the smaller size. It SHALL write every pooled score and the choice. The answer stage SHALL refuse to start without that file.

#### Scenario: Selection reads half A only

- **WHEN** a planted effect exists only in the half-B questions (seed 20261115 split)
- **THEN** the selection MUST be the same as without that effect

#### Scenario: Gap of exactly 0.01

- **WHEN** the 0.6B reranker pools 0.010 below the best reranker size
- **THEN** the selection MUST choose 0.6B

#### Scenario: Search setup missing

- **WHEN** a search setup of any dataset has no scores
- **THEN** the selection step MUST stop and name the setup

### Requirement: Parallel and serial runs write the same row files

A stage SHALL write its row file and its trace rows in frozen question order, whatever order the calls finish in. With a fixed clock, a run at any concurrency SHALL give row and trace files with the same bytes as a run at concurrency 1.

#### Scenario: Calls finish out of order

- **WHEN** the call for question 3 finishes before the calls for questions 1 and 2
- **THEN** the row file MUST hold the rows of questions 1, 2 and 3 in that order

#### Scenario: Same bytes as serial

- **WHEN** one stage runs on stub calls with a fixed clock, once at concurrency 8 and once at concurrency 1
- **THEN** the two row files MUST be byte-identical, and the two trace files MUST be byte-identical

### Requirement: A finished result survives a stop

A result that finishes before an earlier item SHALL be kept on disk at once. A stop SHALL NOT lose it, and `--resume` SHALL write it in its place in the frozen order without a new call.

#### Scenario: Stop with a result held back

- **WHEN** question 3 has finished, question 2 is still in flight, and the stage stops
- **THEN** `--resume` MUST write the row of question 3 from disk without a new call for question 3
