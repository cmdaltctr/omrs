# Tasks

Rules for every code task:

- Work test-first. Write the failing test, run it, and record that it fails for the expected reason. Then write the code and run the test again.
- Keep every file under 500 lines (`tests/test_file_size_ceiling.py`).
- Paths without a folder are in `experiments/35-full-rag-benchmark-2026-11-01/`.
- Run tests with `uv run --no-sync pytest <files> -q`. Run the full suite only after the operator agrees.

## 0. App fixes in OMRS (before the harness groups; operator decision, 2026-11-12)

These tasks change `src/omrs/` and `web/`, so the benchmark measures the shipped app (design D25, D26). Each test is proved to fail on the current code before the fix. Groups 2, 4 and 5 rely on this group.

- [ ] 0.1 Rate-limit classifier (D25). Write failing tests in `tests/unit/test_answer_rate_limit.py` for a new `src/omrs/core/answer/rate_limits.py`:
  - a stub exception with `status_code` 429 or 402 is a rate limit; a 500 error, a timeout and a `ValueError` are not;
  - `Retry-After: 7` gives 7.0 s, `retry-after-ms: 1500` gives 1.5 s, and no header gives `None`;
  - `kind` is `rate_limit` for a 429 and for a 402 with `Retry-After`, and `out_of_credit` for a 402 with no `Retry-After`;
  - a real `openai.RateLimitError` (429) and a real `openai.APIStatusError` (402), each built on an `httpx.Response`, classify correctly.

  Prove they fail (no module). Then implement by duck typing; core imports no provider library. Verify: the tests pass.
- [ ] 0.2 Typed result (D25). Write failing tests in the same file:
  - a seam that raises a 429 with `Retry-After: 7` gives, through `Engine.answer` on the standard path, status `error`, `failure_stage` `generation`, `answer` null, the evidence, and `rate_limited` `{"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 7.0}`;
  - a 402 with no `Retry-After` gives `kind` `out_of_credit`, and `error` tells the user to top up the provider account;
  - the user-profile graph path gives the same record;
  - a non-rate-limit failure has no `rate_limited` key, and its `error` text is unchanged.
  - With claim verification on, a judge seam that raises a 429 with `Retry-After: 30` keeps the answer and its status, sets `verification_skipped` to the fixed reason, and adds `verification_rate_limited` `{"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 30.0}`, on both paths. A judge 402 with no `Retry-After` gives `kind` `out_of_credit` and a top-up reason. A judge failure that is not a rate limit adds no record and keeps today's reason.

  First run the judge test on today's code and record that it fails: there is no record, and the reason is `verification failed: RateLimitError: ...` (`src/omrs/core/answer/verify.py:461-463`).

  First run the 429 test on today's code and record that it fails: the result has no `rate_limited` key and `error` is `Generation failed: RateLimitError: ...` (`src/omrs/core/answer/stages.py:185`). Then add `rate_limited` to `SynthesisOutcome` and `stage_failure_result`, and pass it at `core/answer/pipeline.py:302` and `core/answer/graph_adapters.py:274`. Add `rate_limited` to `VerificationFields`, classify in the catch of `run_verification_stage`, and add `verification_rate_limited` in `answered_result`. Verify: the tests pass, and `tests/unit/test_answer_seams.py`, `tests/unit/test_answer_seams_parity.py` and `tests/unit/test_answer_pipeline_stages.py` still pass.
- [ ] 0.3 Short 402 retry (D25). Write failing tests with an injected sleep:
  - a 402 with `Retry-After: 5`, then a success, waits 5 s once and returns status `ok` with no `rate_limited`;
  - a 402 with `Retry-After: 5` on every attempt makes 3 attempts in all, then gives the typed error;
  - a 402 with `Retry-After: 120` makes 1 attempt and gives `kind` `rate_limit`;
  - a 402 with no header makes 1 attempt and gives `kind` `out_of_credit`;
  - a 429 makes 1 attempt (no third retry layer) and gives the typed error;
  - `completion_calls` counts rounds, not retried attempts;
  - a judge that is a plain completion seam follows the same 402 rule.

  Prove they fail, then implement the retry inside `synthesise_answer`'s seam wrapper and around a plain judge seam in `verify_answer` (`core/answer/stages.py:291-293`). Verify: the tests pass.
- [ ] 0.4 Contract and callers (D25). Write failing tests first:
  - in `tests/unit/test_answer_response_contract.py`, a rate-limited generation result and a result with `verification_rate_limited`, both from the real builders, conform; a record with an extra key or an unknown `kind` is refused (today it fails: the schema is closed);
  - MCP `answer_documents` with a 429 seam returns the error result with `rate_limited` and does not raise (gotcha 1);
  - a new `web/src/chat/answerStatus.test.ts`: `failureLine` of a result with `kind` `rate_limit` says that the provider is limiting requests and to wait, then Retry; with `kind` `out_of_credit` it says to top up the provider account; a result without the record keeps today's lines.

  Prove they fail, then add `rate_limited` and `verification_rate_limited` (one shared record schema) to `AnswerResponse` in `src/omrs/transports/api/openapi.yaml`, the optional field to `web/src/api/documents.ts`, and the line to `web/src/chat/answerStatus.ts`. Leave `web/src/chat/useChatSession.ts:157` unchanged, so an error is never saved as a turn. Verify: the Python tests, `tests/test_openapi_conformance.py` and the web test pass.
- [ ] 0.5 Read-only native query (D26). Write failing tests in `tests/test_native_sparse_read_only.py` on a temporary LanceDB store:
  - a native query on a collection whose FTS index has an unindexed row leaves `table.version` and the FTS row counts unchanged, and still returns the unindexed row; a row deleted after the index is not returned (this also pins the corrected wording of "Existing collections are usable without re-ingestion", D26 item 7);
  - a native query on a collection with no FTS index creates no index; the hybrid pipeline warns, serves BM25 for that query, and the warning names the ingest remedy;
  - two threads that query one collection at once leave the table version unchanged.

  First run them on today's code and record that the table version changes (`src/omrs/core/vectordb/lancedb/fts.py:180`, `:192`). Then remove both calls from `query_native_sparse`. Verify: the tests pass, and `tests/test_lancedb_native_fts_contract.py` and `tests/test_native_sparse_backend.py` still pass.
- [ ] 0.6 Prepare at ingest (D26). Write failing tests:
  - with the resolved backend `native`, `ingest_path_async` ends with an FTS index on the collection; after a second ingest that adds rows, the index has zero unindexed rows;
  - an ingest that writes nothing still prepares the index of an existing collection;
  - with the backend `bm25`, the ingest creates no FTS index;
  - a prepare failure logs a warning and leaves the ingest result unchanged;
  - `prepare_native_sparse` on a Chroma store does nothing and does not raise.

  Prove they fail, then add `prepare_native_sparse` to `VectorStore` (no-op) and `LanceFTSMixin` (create, then refresh), and call it once at the end of `ingest_path_async`. Keep `core/ingestion/pipeline.py` under 500 lines (458 now); if the call does not fit, put a helper in `core/ingestion/writer.py`. Verify: the tests pass, and `tests/test_sparse_cache_freshness.py` still passes (gotcha 14).
- [ ] 0.7 Change the mixed-coverage warning (`src/omrs/core/retrieval/sparse_dispatch.py:157`) to name the next ingest, not the next query, and update the lifecycle text in the `fts.py` module docstring. Write the failing test on the warning text first. Verify: the test passes.
- [ ] 0.8 Docs drift check for both fixes. Search `docs/guides/` for "first native query", "refreshes the index", "Generation failed", `failure_stage` and `rate`. Update at least `docs/guides/reranker.md:135-144` (FTS lifecycle), `docs/guides/mcp-tools.md:181-186` and `docs/guides/cli-reference.md:172` (the `rate_limited` and `verification_rate_limited` records, and both kinds), and `docs/guides/architecture.md:314`. Verify: a second search finds no stale statement.
- [ ] 0.9 Run the group's test files together with `tests/test_file_size_ceiling.py`. Verify: all pass. The tripwire count is updated once, in task 11.1.
- [ ] 0.10 After the merge into `v3`, ask the operator, then reinstall the live app in `~/.omrs` with the locked constraints. Verify: the reinstall resolves the merged `v3` commit, and one chat answer in the live app returns `ok`.

## 1. Make room in the stage module

- [ ] 1.1 Move `answer_stage`, `judge_stage` and their helpers from `stages35.py` to a new `answers35.py` without a change in behaviour. Point `run_arms.py` and the tests at the new module. Verify: `tests/test_experiment35_stages.py` and `tests/test_experiment35_run_arms.py` pass unchanged except for import lines, and `stages35.py` drops below 300 lines.

## 2. Shared gate for hosted calls (`experiments/_lib/hosted_calls.py`)

- [ ] 2.1 Write failing tests in `tests/test_experiment_hosted_calls.py` for the concurrency limit. A gate with limit 4 and 20 stub calls never has more than 4 in flight. A gate with limit 1 runs calls in submission order. Prove they fail (no module). Then build the gate with one semaphore per role. Verify: the tests pass.
- [ ] 2.2 Write failing tests for rate-limit classification:
  - a stub exception with `status_code` 429 or 402 is a rate limit;
  - a 429 with Z.AI body code 1302 is a rate limit;
  - an answer result that carries the OMRS `rate_limited` record, built by the real result builder after task 0.2, is a rate limit, and its `retry_after_seconds` is the wait;
  - an answer error result without the record is not a rate limit, even when its `error` text names 429 (the harness never reads the text);
  - a 500 error or a timeout is not.

  Prove they fail, then implement the classifier. Verify: the tests pass. Delete the 429 branch and confirm that the matching test fails.
- [ ] 2.3 Write failing tests for waits and the stop. Use an injected sleep and random source.
  - `Retry-After: 7` waits 7 s.
  - `retry-after-ms` is read.
  - A `Retry-After` above 600 s raises `RateLimitStop` at once.
  - With no header, the backoff is base 5 s, factor 2, cap 120 s, with equal jitter.
  - After `--rate-limit-attempts` (default 6) tries, the gate raises `RateLimitStop`.
  - An HTTP 402 with no `Retry-After`, or an answer record with `kind` `out_of_credit`, raises `RateLimitStop` at once, with no wait, no second attempt and a top-up message.
  - A non-rate-limit error passes through unchanged.

  Prove they fail, then implement. Verify: the tests pass.

## 3. Ordered rows that survive a stop (`experiments/_lib/ordered_rows.py`)

- [ ] 3.1 Write failing tests in `tests/test_experiment_ordered_rows.py`:
  - results that finish in the order 3, 1, 2 are committed to the row file and the trace file as 1, 2, 3;
  - a result finished ahead of an unfinished item is in `<stage>.pending.jsonl` at once, flushed;
  - after a simulated stop, a resume commits pending results in order and asks for calls only for items with neither a row nor a pending result;
  - the done-marker is written after the last commit, and the pending file is then removed;
  - a stub stopped after its call returned and before the pending write is called again once on resume, and the stage trace counts one resent call (`resent_calls` 1); a stub whose result reached the pending file is not called again, and its `resent_calls` stays 0; no resend depends on the answer content.

  Prove they fail, then implement on top of `outputs35.RowFile`. Verify: the tests pass.

## 4. Parallel answer and judge stages

- [ ] 4.1 Add `--answer-concurrency`, `--chat-concurrency`, `--ragas-concurrency` and `--rate-limit-attempts` to `run_arms.py`. Use the starting defaults 16, 4, 16 and 6 from one constants block in `arms.py`; task 9.2 replaces them with the measured values before the freeze. First write failing tests:
  - the parser accepts values of 1 or more and refuses 0;
  - the dry-run plan prints the resolved values;
  - the trace `effective_settings` holds them;
  - the command passed to `guard_run` holds every resolved value, also when a default applied.

  Verify: the tests pass. Move the parser to `cli35.py` if `run_arms.py` nears 500 lines.
- [ ] 4.2 Write failing tests in `tests/test_experiment35_parallel_answers.py`:
  - the answer stage calls `search` once per question, one at a time, and passes the returned rows to `answer`;
  - each question's evidence chunk IDs are the same at concurrency 8 and 1;
  - a retrieval failure keeps an error row and sends no answer call;
  - with a fixed clock, `answer.jsonl` is byte-identical at concurrency 8 and 1, and `traces.jsonl` is byte-identical once the concurrency values are removed from its trace settings; each trace still records its own value.

  Prove they fail, then wire the answer stage through the answer gate and the ordered rows. Verify: the tests pass.
- [ ] 4.3 Write failing tests for the rate-limit path of the answer stage:
  - a stub answer that returns an error result with the `rate_limited` record twice and then succeeds gives one success row;
  - a stub that always returns 429 gives no row for that question, no done-marker, and `main()` exit code 5;
  - `--resume` then sends calls only for questions without a row or a pending result, and so sends the rate-limited question again;
  - a non-rate-limit error still gives an error row.

  First run the 429 tests against today's `stages35.answer_stage` and record that they fail because the rate limit is saved as an error row and skipped on resume.

  Prove they fail, then implement `EXIT_RATE_LIMIT = 5` in `run_arms.py`. Verify: the tests pass. Under `--arm all`, a child exit code 5 stops the later arms.
- [ ] 4.4 Write failing tests in `tests/test_experiment35_parallel_judges.py`:
  - the `chat` judge stage judges several answers at once, never above `--chat-concurrency` calls in flight;
  - `clef_flash` never has more than one call in flight (Granite Guardian was dropped on 2026-11-12 and leaves `JUDGE_NAMES`);
  - the judge rows are byte-identical at concurrency 4 and 1 with a fixed clock, and the traces are byte-identical once the concurrency values are removed from their trace settings;
  - a `chat` 429 on every attempt stops with exit code 5 and saves no row for that answer;
  - a `chat` non-rate-limit failure still exits with code 4, after the calls in flight have gone to the pending file.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 4.5 Update the docstrings of `run_arms.py` (options, exit code 5) and `answers35.py` (ordering and resume rules). Verify: `uv run --no-sync python experiments/35-full-rag-benchmark-2026-11-01/run_arms.py --help` lists the new options.
- [ ] 4.6 Pin the hybrid arm's sparse backend (operator decision, 2026-11-12; design D8). Write failing tests in `tests/test_experiment35_run_arms.py` (or a new test file if it nears 500 lines):
  - `arms.settings_values` for every hybrid-on setup (the hybrid arm before the 2026-11-12 redesign) holds `retrieval.hybrid_sparse_backend: bm25`;
  - a hybrid-on setup's trace `effective_settings` names `bm25`;
  - with `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` in the environment, a hybrid-arm stage stops with a setup error (exit code 2) before any query and names the setting.

  Prove they fail, then add the value in `arms.settings_values` (`arms.py:149`) and to `_resolved` (`run_arms.py:182`); `router_env.check_resolved` (`experiments/_lib/router_env.py:295`) gives the refusal. Verify: the tests pass.

## 5. Replicate runs: local folders, index folder, seal and machine record

- [ ] 5.1 Write failing tests for `--local-dir`:
  - with it, `config/` and `state/` go under the local folder and nothing new appears in `<out>` except run outputs;
  - without it, the paths are the same as before (`outputs35.py:61-73`).

  Prove they fail, then implement in `outputs35.Layout` and `run_arms._configure`. Verify: the tests pass.
- [ ] 5.2 Write failing tests for `--index-from`:
  - the store, the index markers and the fingerprint are read from the index folder;
  - outputs go only to `--out-dir`;
  - a stage that would write under the index folder fails the test's file-set check.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 5.3 Write failing tests for `--qids`:
  - two named IDs select only those questions, in frozen order;
  - the run counts as a smoke run, with no run-record line;
  - an unknown ID stops with exit code 2 and names the ID before any call.

  Prove they fail, then implement in `run_arms.py` and `datasets35.py`. Verify: the tests pass.
- [ ] 5.4 Write failing tests for the `seal` stage, on a temporary LanceDB store with two small collections:
  - it seals one index (design D32): it refuses when that index has no `.done-ingest.json` on a dataset, and names the index and the dataset;
  - it creates and refreshes no full-text index: the table version is the same before and after the seal;
  - where a hybrid-on setup resolves `native`, it refuses and names the collection when the FTS index is missing or has unindexed rows;
  - it writes `<dataset>/<index>/index-fingerprint.json` with the table version, the dataset epoch, the resolved sparse backend of the index's hybrid-on setups, and the indexed and unindexed row counts (or none).

  Prove they fail, then add `seal` to `arms.STAGES` and implement it. Verify: the tests pass.
- [ ] 5.5 Write failing tests for the fingerprint checks in search, answer and judge stages:
  - on a temporary LanceDB store, a hybrid search stage on a sealed collection leaves the table version and the full-text index counts unchanged, with the `bm25` and the `native` backend (the OMRS read-only query is task 0.5);
  - a missing fingerprint refuses the stage before the first query, and so does a missing full-text index when the stage's backend is `native`;
  - a hybrid stage that resolves another sparse backend than the fingerprint refuses and names both;
  - a table version that changes during a stub stage fails it with exit code 2 and no done-marker;
  - a clean stage records both checks in its done-marker;
  - a search, answer or judge stage that writes into the shared output folder refuses without a passing `rebuild.json` for its dataset and names the dataset, while a stage with `--index-from` and another output folder is not blocked.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 5.6 Write failing tests for the environment record (design D19), with injected readers for `nvidia-smi`, `EXP35_POD_IMAGE` and the llama.cpp runtime check:
  - `seal` writes `<out>/environment.json` with the GPU model, the image, the llama.cpp build and the SHA-256 of each plan GGUF;
  - each stage that runs a model, sends a model call or reads the index appends the host name, `RUNPOD_POD_ID` (or null) and its environment record to `run<n>/machine.jsonl` at start;
  - a stage refuses before any call when a field differs from `environment.json` or is missing (for example on a Mac without `nvidia-smi`), and names the field;
  - a stage refuses an `EXP35_POD_IMAGE` value without an `@sha256:` digest;
  - `join35.py`, determinism and `refusals35.py report` run without an environment record.

  Prove they fail, then implement. Verify: the tests pass.

## 6. Join step and the determinism gate

- [ ] 6.1 Write failing tests in `tests/test_experiment35_join.py` for `join35.py`, on a built fixture folder with 2 datasets, 2 arms and 3 runs:
  - a complete folder gives `join.json` `ok: true`;
  - a folder with `search` done-markers in run 1 only (design D34) passes, and a search setup with no run-1 `search` done-marker fails and names the dataset, setup and stage;
  - a missing `judge-chat` done-marker in one run fails and names the dataset, arm, run and stage;
  - different `answer.key.json` contents across runs fail and name the fields;
  - a done-marker with a changed fingerprint check fails;
  - a run with no run-record line fails;
  - a dataset with no passing `rebuild.json` fails and names the dataset;
  - `--smoke --runs 1` on a one-run folder checks that run only and writes a report marked smoke, which determinism and statistics refuse;
  - a run with no `ragas` or `claimkinds` done-marker, or with fewer `ragas.jsonl` rows than answers, fails and names the dataset, arm, run and stage;
  - a run whose machine record differs from `environment.json` in the GPU model, image, llama.cpp build or a GGUF hash fails and names the run and field.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 6.2 Write failing tests for the run-record merge:
  - three pod files merge into the experiment's `output/run-records.jsonl` in start-time order after the existing lines;
  - a second merge adds nothing;
  - no earlier line changes (compare bytes).

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 6.3 Write failing tests for `determinism_stage`:
  - it refuses without a passing `join.json` and names the join step;
  - with one, `determinism.json` lists the machines of each run from `machine.jsonl`.

  Prove they fail, then implement. Verify: the tests pass. Update the existing determinism tests to build a join report first.
- [ ] 6.4 Write failing tests in `tests/test_experiment35_rebuild.py` for `rebuild35.py` (G2, Exp 35 task 4.2):
  - two search files with the same ranked IDs give `rebuild.json` with `ok: true` and the number of questions compared;
  - one question with IDs in another order fails, names the question and exits with code 3;
  - a question with a row on one side only counts as a mismatch;
  - the tool reads only the two named `search.jsonl` files and writes only `<out>/<dataset>/rebuild.json`.

  Prove they fail, then implement with `compare_runs` from `experiments/_lib/determinism.py`. Verify: the tests pass, and `--help` shows the two inputs and the output folder.

## 7. Ragas stage in the main harness (`ragas35.py`)

- [ ] 7.1 Write failing tests in `tests/test_experiment35_ragas.py` with stub metrics and a stub seam:
  - `--stage ragas` reads only `run<n>/answer.jsonl` of the named run, and writes `run<n>/ragas.jsonl` and `.done-ragas.json` there, so each replicate pod scores its own run;
  - it refuses before any call when the answer stage has no done-marker;
  - a wrong Ragas version stops before any call and names both versions;
  - an answer with an error or no text gets a "not judged" row and no call;
  - a refusal answer is scored with every metric like any other answer;
  - each worker has its own recording seam, so the call records of two answers scored at once never mix;
  - rows are byte-identical at concurrency 8 and 1 with a fixed clock.

  Run the shared-state test first against a direct use of one pre-freeze `RecordingSeam` by two concurrent answers, and record that it fails (the calls mix). Then implement by importing `prefreeze/ragas_stage.py` and `prefreeze/measure_lib.py` without changing them. Verify: the tests pass, and `git diff --stat` shows no change under `prefreeze/`.
- [ ] 7.2 Write failing tests for Ragas rate limits and resume:
  - a metric whose seam raises 429 on every attempt saves no row and exits with code 5 (run this test first against the pre-freeze `judge_answer` path and record that it fails: today the 429 is saved as the metric error `RateLimitError`);
  - `--resume` after a stop at 40 of 100 answers sends calls for the other 60 only;
  - a non-rate-limit metric error is saved in the row as today.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 7.3 Add `--ragas-host` (required for this stage) and `--ragas-venv`. The judge is built like `prefreeze/measure_live.py:157-192`, and the embedding endpoint and runtime are recorded in the row header. Write the failing tests first: a missing host refuses before any call, and the dry run prints the judge model, host, reasoning, temperature, seed and Ragas version. Verify: the tests pass.

- [ ] 7.4 Write failing tests for the Ragas embeddings, with an injected router and runtime check:
  - the stage asks the local router for the plan's 4B embedding file only, after the local judge stages have released the router;
  - it calls the llama.cpp runtime check for that file before the first paid call, and a wrong build or file hash stops it;
  - `.done-ragas.json` records the embedding endpoint, the build and the file hash.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 7.5 Check the Ragas refusal penalty in the source. Do this early, before task 7.1.  Read the `AnswerRelevancy` code of Ragas 0.4.3 in the pinned Ragas environment, and query Context7 (`/vibrantlabsai/ragas`). Find whether a non-committal answer scores 0. Verify: `protocol.md` section 4.4 states the result with the file and line. If the source does not confirm it, `protocol.md` lists it as an open item and no text claims the penalty. Either way, the report states the result.

## 8. Claim kinds, classifier gate and refusal report (`refusals35.py`)

The classifier is the fixed-prompt LLM `openai/gpt-oss-120b`, pinned (operator decision, 2026-11-12; design D14).

- [ ] 8.1 Before any labelling, write the gate into `protocol.md` section 4.4 as part of the dated pre-freeze amendment (2026-11-12):
  - the thresholds: agreement on refusal against not refusal of at least 0.90, and refusal recall of at least 0.90;
  - the sample seed 20261112 and its size of 100;
  - the strata: dataset, and the pre-freeze regular expression flag;
  - the rule that a failed gate blocks the freeze of the classifier.

  Verify: the operator accepts the text, and the commit that holds it is dated before the labelling page is first opened.
- [ ] 8.2 Write failing tests for claim alignment:
  - claims split again from the saved answer with `split_claims` match the judge row's verdict count and order;
  - a count mismatch stops the step and names the dataset, arm, run and question.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 8.3 Write failing tests for `refusals35.py sample --seed 20261112 --n 100`:
  - it reads only the valid smoke claims (BioASQ, FinanceBench, FreshStack rerun) and refuses the invalid first FreshStack smoke folder;
  - it takes about a third from each dataset, half flagged by the pre-freeze regular expression and half not; a stratum with too few claims gives all of them, and the other stratum of that dataset fills the gap;
  - it records each stratum's size and sampling fraction for the weights;
  - the same seed gives the same claims in the same order;
  - it writes the sample with no kind and no verdict;
  - it writes the list of smoke claims outside the sample for prompt examples.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 8.4 Write failing tests for `refusals35.py page`. It writes one static HTML file into the restricted output folder with the question and the claim of each sampled item, and four choices: factual claim, refusal, mixed, can't tell. It holds no kind, no verdict and no network address. It saves the labels as a JSON download, and keeps a draft in browser storage inside `try`/`catch`. Prove they fail, then implement. Verify: the tests pass, and the operator opens the page and saves a test label file.
- [ ] 8.5 Write failing tests for the classifier with a stub LLM:
  - the prompt holds the three kinds and examples taken only from the claims outside the sample (a test checks that no example is a sample claim);
  - the input is the question and the claim, never evidence or a verdict;
  - the version is the SHA-256 of the prompt, model id, host, reasoning, temperature and seed;
  - `--stage claimkinds` reads one run folder's answers and judge rows, and writes `run<n>/claim-kinds.jsonl` and `.done-claimkinds.json` there; `--resume` skips saved claims;
  - the stage runs the environment check like any model stage (task 5.6);
  - calls go through the hosted gate with `--classify-concurrency` (default 16), and a 429 on every attempt saves no kind and exits with code 5;
  - an unreadable reply is saved as `unreadable` and counts as a gate miss.

  Prove they fail, then implement with `openai/gpt-oss-120b` on one pinned OpenRouter host, reasoning `low`, temperature 0 and the plan seed. Verify: the tests pass.
- [ ] 8.6 Write failing tests for `refusals35.py gate` against a label file (it reads saved files only and runs on the Mac):
  - it gives stratum-weighted agreement on refusal against not refusal and refusal recall, with the unweighted values, the refusal count and the "can't tell" count;
  - it scores the pre-freeze regular expression as a baseline;
  - it writes `gate.json` with pass only when both thresholds hold;
  - mixed and factual labels both count as not refusal.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 8.7 Tell the operator before the paid run (about 100 classifier calls), then run the gate. The operator labels the sample on the page, blind. Run the classifier on the sample as a stage on the 4090 pod (the build pod), copy the saved kinds back, then run `refusals35.py gate` on the Mac. Verify: `gate.json` exists. On a pass, `protocol.md` names the frozen classifier version and the gate figures with the date. On a fail, nothing is frozen and the operator chooses the next step.
- [ ] 8.8 Add `cohen_kappa(a, b)` to `experiments/_lib/stats_d6.py` (approved 2026-11-12). Write the failing tests first in the stats test file:
  - the known-answer test: a 2 x 2 table with 20, 5, 10 and 15 items gives kappa 0.40 (observed agreement 0.70, chance agreement 0.50);
  - perfect agreement gives 1.0;
  - empty or unequal inputs raise `ValueError`;
  - chance agreement of 1 (one label only) returns NaN.

  Prove they fail, then implement. Verify: the tests pass, and `stats_d6.py` stays under 500 lines.
- [ ] 8.9 Write failing tests for `refusals35.py report` on a fixture joined folder with saved per-run kinds (it reads saved files only and runs on the Mac):
  - it refuses without a passing join or without a frozen classifier version;
  - it counts claim texts that got different kinds in different runs, and uses each run's own kinds;
  - primary faithfulness per answer setup and checker (GLM-5.3, Clef-Flash) uses factual and mixed claims only (H-CC and Granite Guardian dropped, 2026-11-12);
  - it writes the refusal rate per answer setup and dataset, marked primary descriptive;
  - it writes each checker's unsupported rate on refusal claims, and the Clef-Flash against GLM-5.3 kappa on refusal and on factual claims per dataset;
  - it writes faithfulness on all claims, marked secondary robustness;
  - it writes per-checker bounds where only that checker's refusal verdicts change, with the lowest and highest faithfulness per answer setup and dataset;
  - a question with no factual claim leaves that dataset's bootstrap and is counted.

  Prove they fail, then implement with `experiments/_lib/stats_d6.py` (`wilson`, `paired_bootstrap`). Verify: the tests pass.

## 9. Image pin and pre-freeze test pod session (before G7)

- [ ] 9.1 Resolve the digest of `runpod/base:1.6.0-cuda1281-ubuntu2404` and record it before the freeze. Record `runpod/base@sha256:<digest>` in `protocol.md` section 7 and in the `plan.json` `runtime` block. Make the Mac pod-creation script pass that one value as the pod image and as `EXP35_POD_IMAGE`. No such script exists in the repository today. If the operator keeps it outside the repository, record its path and the line that sets the image in `protocol.md`. Verify: the digest read from the registry twice gives the same value, and a dry run of pod creation shows the same pinned value for the image and the variable.
- [ ] 9.2 Run the pre-freeze test pod session (design D24) after groups 0 to 8 and 12 to 14 are merged and their tests pass. Quote the pod price and the expected paid cost (about 6 h, about $5 of pod time plus a few dollars of hosted calls) and wait for the operator's go before creating the pod. Use the standard RTX 4090 pod with the pinned image from task 9.1, its own smoke folder and its own small indexes (`--limit`, `--corpus-sample`); never the main output folder.
  1. End to end, as run 1: ingest, `seal`, search (with a reranker-on and a hybrid-on setup), parallel answers, `clef_flash`, `chat`, `ragas`, `claimkinds`, then `join35.py --smoke --runs 1`. Run the rebuild check once on a toy rebuild of one small index.
  2. FreshStack recheck: `--qids 77536364,77762811` through answer and the two judges in every answer-setup shape (each chunk size, reranker on and off, hybrid on and off). Pass rule: every `answer-summary.json` has `failed` 0 and every judge summary has `errors` 0.
  2a. Reranker files (design D24 revision, item 1): for each Qwen3-Reranker GGUF candidate, a relevant pair scores near 1 and an irrelevant pair near 0, and the ranking of 20 query-passage sets matches the model card's transformers recipe. Record the result per file.
  2b. Reranker throughput at 0.6B, 4B and 8B on 100-candidate pools at 512-, 1,024- and 2,048-token passages; the 8B embedder and the 8B reranker loaded together (peak VRAM, any swap); index build time per chunk size on a fixed slice of each corpus for each embedder.
  3. Calibration: answers at 16, `chat` at 4, Ragas at 16, `claimkinds` at 16. Record per role the 429 and 402 counts, the waits, the stops and the calls per minute. Halve a value that hit a rate-limit stop and repeat that role once. Check that each answer's evidence chunk IDs equal the same run's search IDs. Measure wall seconds per answer per stage and the reported `cost_usd` per answer.
  4. The first budget check (design D23 revision): measured build hours per chunk size times 9 indexes, plus the search stage from the measured reranker throughput, plus three replicate pods at the measured hours, all times the pod price, plus the hosted cost per answer times 41,760. Above the $975 ceiling, the operator decides before the freeze.
  5. Copy the session outputs to the Mac, then delete the pod.

  Verify: steps 1 and 2 pass with zero errors; a dated calibration note in `protocol.md` gives the measured values, the counts, the hours per replicate pod and the extrapolated total; design.md D22 holds the measured rates; the `arms.py` defaults equal the measured values; the pod no longer exists in the RunPod pod list. A failure in step 1 or 2 is fixed in code and the session runs again.

- [ ] 9.3 GPU choice (operator instruction, 2026-11-12; design D24 revision). Before the first measurement, write the decision rule into `protocol.md` section 0: among GPUs that hold the 8B embedder and the 8B reranker together without swapping, choose the lowest projected total GPU cost for the main build and search work (9 index builds per dataset plus 72 search setups); within 10% on cost, choose the faster one. Then, for each candidate (RTX 4090 24 GB, L40S 48 GB, H100 80 GB):
  1. Re-check the live price and stock, quote them, and wait for the operator's go before creating the pod. Use the pinned image (task 9.1).
  2. Run the same fixed job of about 10 minutes: embed a fixed sample of 2,000 chunks (FinanceBench and FreshStack, at 1,024 and 2,048 Qwen3 tokens) with Qwen3-Embedding-8B Q8_0; rerank a fixed set of query-passage pairs with Qwen3-Reranker-8B Q8_0.
  3. Record chunks per second, pairs per second, peak VRAM, whether the 8B embedder and the 8B reranker load together without swapping, the llama.cpp build, the driver version and the image digest.
  4. Delete the pod.

  The 4090 run can be part of the task 9.2 session. Verify: `protocol.md` holds the rule (in a commit dated before the first measurement), the measurements per GPU, the prices with their date, the projected cost per GPU and the choice; the D22 and D23 rows are scaled to the chosen GPU; every main-run pod in the procedure (task 10.1) names that one GPU type; and no candidate pod remains in the RunPod pod list.

## 10. Protocol and procedure

- [ ] 10.1 Write the run procedure into `protocol.md` section 5, and amend the section 4.5 machine decision. Cover:
  - the environment rule: every experiment stage runs on a pod of the one GPU type chosen in task 9.3 (same image, llama.cpp build b11941 and GGUF files), including hosted-only stages; GPU types are never mixed; the earlier 4090 pre-freeze runs were preparation, not results; only steps that read saved files and write checks, statistics or reports run on the Mac;
  - the pod-creation script on the Mac, which passes the one pinned image value (task 9.1) as the pod image and as `EXP35_POD_IMAGE`;
  - the RunPod network volume in one data centre, holding the GGUF files once;
  - the 9 index pods in parallel (design D32): each builds one index (`e<embedder>-c<chunk size>`) for all four datasets into its own store folder and seals it;
  - the `e4b-c1024` rebuild (design D20 revision) as soon as the shared `e4b-c1024` index is sealed, on a tenth pod or on the `e4b-c1024` pod before its search: a fresh process ingests into a separate store, `e4b-c1024-roff-hoff` searches the rebuilt index and the shared index (`--index-from`, separate output folders), and `rebuild35.py` writes `rebuild.json` for each dataset;
  - then each index pod runs its 8 search setups as run 1 into the shared output folder; the guard of task 5.5 makes them wait for a passing `rebuild.json` for each dataset;
  - the G2 stop rule in section 6: if a rebuild check fails, the replicate pods do not start; find the cause, fix it, build the indexes again, then seal and check again;
  - the zero-error recheck of FreshStack `77536364` and `77762811` in every answer-setup shape (`--qids`, `--index-from`, its own output folder); the pass rule: every `answer-summary.json` has `failed` 0, and every judge summary has `errors` 0;
  - the search-stage time of the recheck on the volume, recorded as a check on read speed;
  - on the Mac: score the 72 search setups and run the selection rule (`select35.py`), and write the dated selection note into `protocol.md` section 0.5;
  - the budget re-check after the search stage, with the real pod cost so far and the measured rates; above the ceiling, stop before the replicate pods and ask the operator;
  - the three replicate pods with `--run 1`, `2` and `3`, `--local-dir` on the container disk, and their own checkouts; each pod runs answer (with its own retrieval), the two judges, `ragas` and `claimkinds` for the 15 answer setups on its own run, one stage at a time, with the budget read at each stage end;
  - the expected pod hours from design D22 and D32, as measured by tasks 9.2 and 9.3;
  - the copy-back without `lancedb/`;
  - on the Mac, steps on saved files only: `join35.py`, determinism, the refusal report and statistics;
  - stopping each pod as soon as its work is copied.

  Verify: every command in the procedure runs with `--dry-run` or `--help` as written.
- [ ] 10.2 Write the budget into `protocol.md` section 0.8 (replaces Exp 35 task 1.11 and the $250 cap of the first 2026-11-12 decision): the estimate of design D23 updated with the measured values of tasks 9.2 and 9.3, and the ceiling of 1.5 x the estimate ($975 before measurement), pods and hosted calls together. State the three checks (design D23): before the freeze, on the index pods after the search stage (stop before the replicate pods), and at each stage end during the replicate pods. Set the OpenRouter key's credit limit to the hosted share of the ceiling. Verify: `protocol.md` states the estimate, the ceiling, the checks and the date, and Exp 35 tasks 1.11 and 4A.5 are ticked with a pointer to it.
- [ ] 10.3 Write the dated pre-freeze amendment (2026-11-12) into `protocol.md` section 4.4, and add a matching amendment note to ADR-119. It must give:
  - the three claim kinds, with mixed sentences and negative findings counted as factual claims;
  - primary faithfulness on factual claims only, with the reason (a refusal is a statement about retrieval, and the checkers grade refusals very differently);
  - the refusal rate per answer setup and dataset as a primary descriptive outcome, and each checker's verdicts on refusals;
  - faithfulness on all claims, and the per-checker bounds, as secondary robustness results;
  - the smoke evidence: 15 of 278 BioASQ, 33 of 143 FinanceBench, 20 of 383 FreshStack rerun, and the checkers' different grading of refusals (Granite Guardian, since dropped, said unsupported on 67% to 94%);
  - that the rule was first written for H-CC (2026-11-11), and that the 2026-11-12 redesign dropped H-CC and Granite Guardian, so the rule now stands on its own (ADR-119 gets the matching note);
  - that the 76% figure from the invalid first FreshStack smoke is not evidence;
  - that Ragas answer scores keep refusals.

  Verify: the operator reads and accepts the text.
- [ ] 10.4 Write the concurrency options, the rate-limit exit code 5 and the stop-and-resume rule into `protocol.md` sections 5 and 7. The values are the measured ones from task 9.2. Verify: the values match the `arms.py` constants and the calibration note.
## 11. Integration checks

- [ ] 11.1 Update the clean-base tripwire count in `tests/test_clean_base_tripwire.py`. Diff the collected test IDs against the last pin, not the per-file counts. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.
- [ ] 11.2 Run `./scripts/local_ci.sh` (after the operator agrees to a full run). Verify: the final line reports success, and no step prints `SKIPPED`.
- [ ] 11.3 Run `uv run --no-sync omrs experiments check` and `openspec validate exp35-main-run-readiness --strict`. Verify: both pass.

Group 11 runs last, after groups 12 to 15 below.

## 12. App addition C: llama.cpp reranker backend (redesign, 2026-11-12; design D27)

Architecture invariant 11: one new file and one `register()` line, no branch on strategy names. Each test is proved to fail on the current code first.

- [ ] 12.1 Write failing tests in `tests/unit/test_reranker_llamacpp.py`:
  - `registry.get("reranker_llamacpp")` resolves `LlamaCppReranker`, and importing the registry does not import the module;
  - `resolve_reranker_backend("llamacpp")` returns it; `"vllm"` still raises `KeyError` naming the three accepted names;
  - settings accept `retrieval.rerank_backend: llamacpp`, and an unknown value fails at startup naming `onnx`, `torch` and `llamacpp`.

  Prove they fail (no module, value refused by `src/omrs/config/rules.py:41`). Then add the file, the `register()` line in `registry.py`, the map entry in `backend.py` and the accepted value. Verify: the tests pass, and `tests/unit/test_reranker_backend*.py` still pass.
- [ ] 12.2 Write failing tests against a stub HTTP server on a free port:
  - one `POST /v1/rerank` per query, with the model name, the query and the candidate texts in input order;
  - the results come back sorted by `relevance_score`, truncated to `top_k`, each with `_reranked` true and a score in (0, 1];
  - the score transform follows the `/v1/rerank` score that llama.cpp build b11941 returns, as read from its server source (probability or raw logit), pinned by a test with fixed numbers; task 9.2 step 2a then checks it on the real files as an acceptance gate, and a mismatch reopens this task before the freeze;
  - an empty candidate list sends no call;
  - a refused connection, an HTTP 500, an unknown model and a reply with a missing index each return the inputs un-reranked with `_reranked` false and a `last_failure_reason`, and never raise.

  Prove they fail, then implement `rerank` with the HTTP client OMRS already uses. Verify: the tests pass.
- [ ] 12.3 Write failing tests for construction: `build_reranker_from_settings` with `rerank_backend` `llamacpp` builds the backend through its `from_settings` class method with `retrieval.rerank_model` and `llamacpp_router_url`; the ONNX and torch backends keep today's constructor call; `compose.build_reranker()` and the lazy pipeline path give the same backend. Prove they fail, then implement the duck-typed call in `backend.py`. Verify: the tests pass, and `backend.py` holds no `if` on a backend name for this.
- [ ] 12.4 Write a failing test that a `llamacpp_models` entry with preset `embeddings: true` and `pooling: rank`, listed but assigned to no role, gives no role problem and appears in the router's `models.ini`. Prove it fails or record that it already passes, then fix if needed. Verify: the test passes.
- [ ] 12.5 Write a failing end-to-end test: a search with `rerank=True` and `rerank_backend` `llamacpp` against the stub router reranks the candidate pool (100 by default, `policy.py:63-67`) and records `rerank_backend` `llamacpp` in the diagnostics. Prove it fails, then wire what is missing. Verify: the test passes.
- [ ] 12.6 Docs drift check: add the `llamacpp` backend to `docs/guides/reranker.md` and `docs/guides/configuration.md`, with the router preset (`pooling: rank`) and the fixed default instruction. Verify: a search for `rerank_backend` in `docs/guides/` finds no list without `llamacpp`.
- [ ] 12.7 Run the group's tests with `tests/test_file_size_ceiling.py` and the import-linter contracts. Verify: all pass.

## 13. Setups, settings and datasets in the harness (redesign, 2026-11-12; design D28, D29, D32)

- [ ] 13.1 Rewrite the arm table in `arms.py` as a setup table (design D28). Write failing tests in `tests/test_experiment35_arms.py` first:
  - the table has 72 setups with names `e<embedder>-c<chunk>-r<reranker>-h<hybrid>` and 9 indexes; no name holds a profile name; the six old arm names are gone;
  - each setup's index and collection names follow the pattern; `e0.6b` loses its dot in the collection name;
  - `settings_values` for `e8b-c2048-r4b-hon` holds `chunking.chunk_size` 2048, `chunking.markdown_chunk_size` 2048, `chunking.chunk_overlap` 307, the Qwen3 tokenizer identity, `retrieval.rerank_backend: llamacpp`, the 4B reranker model, `retrieval.hybrid_sparse_backend: bm25`, and both models in `llamacpp_models` with `llamacpp_router_models_max` 2;
  - overlaps are 77, 154 and 307 for 512, 1,024 and 2,048;
  - a reranker-off setup sets no reranker model and loads one router model;
  - `JUDGE_NAMES` is `clef_flash, chat`;
  - with `CHUNKING__CHUNK_SIZE` or `CHUNKING__MARKDOWN_CHUNK_SIZE` in the environment, a stage stops with exit code 2 before ingest and names the setting.

  Prove they fail, then implement, and update the module docstring to the setup design (no six arms). Verify: the tests pass, and `tests/_exp35_fixtures.py` carries the reranker roles.
- [ ] 13.2 Replace `--arm` with `--setup NAME|all` and `--index NAME` in `run_arms.py` (or `cli35.py`). Write failing tests: `--setup all --stage search` plans 72 setups in a fixed order; `--index e4b-c1024 --stage ingest` plans one ingest per dataset; `--stage search --index e4b-c1024` plans that index's 8 setups; an unknown name exits with code 2. Verify: the tests pass and `--help` shows the options.
- [ ] 13.3 Per-index stores (design D32). Write failing tests: `Layout` puts each index's store under `<out>/stores/<index>/lancedb`; an ingest writes only there; the seal fingerprint is `<out>/<dataset>/<index>/index-fingerprint.json`; two ingests of different indexes into one output folder at the same time leave each store written by one process only. Prove they fail, then implement in `outputs35.Layout`. Verify: the tests pass.
- [ ] 13.4 Legal RAG Bench loader (design D29). Write failing tests with a small fixture of both configs: 100-row shape, gold `relevant_passage_id`, passages written once as `<id>.md` holding title, text and footnotes, with a leading `#` on any line escaped, frozen seeded order, file SHA-256 check, and a stop that names a missing gold passage. Prove they fail, then implement in `datasets35.py`. Verify: the tests pass.
- [ ] 13.5 FreshStack 203 queries and public corpus (operator decision, 2026-11-13). Write failing tests: the loader drops the 20 continuity queries; the corpus holds no `continuity/` file and no overlay runbook; `datasets35.py` has no `_FS_OVERLAY` or `_FS_OVERLAY_ID` reference and no expected hash for the overlay; questions `77536364` and `77762811` stay. Prove they fail, then remove the overlay constants, its hash entry, its id mapping and the `continuity/*.md` glob. Verify: the tests pass, the loader reports 203 queries, and the new corpus tree hash is written into `protocol.md` section 4.1.
- [ ] 13.5a BioASQ passages as `.md` (operator decision, 2026-11-13). Write failing tests: `datasets35.py` writes `<id>.md` (not `.txt`), escapes a leading `#` on any line, and maps gold ids without the suffix. Prove they fail, then implement. Verify: the tests pass.
- [ ] 13.5b Qwen3 token counts on all four datasets. Write a failing test that ingests a small fixture of FinanceBench (Markdown PDF text), FreshStack, BioASQ and Legal at 512, 1,024 and 2,048 tokens and asserts: every chunk has at most the level's Qwen3 token count (pinned tokenizer revision); every dataset goes through the model-token-aware Markdown path; the cl100k counter is never called (patched to raise). Prove it fails on the `.txt` passages, then pass it after 13.4 and 13.5a. Verify: the test passes.
- [ ] 13.6 FinanceBench number match (design D29). Write failing tests with known pairs: "$1,577 million" against "$1.58 billion" passes; "12.5%" against "12.5 percent" passes; "(3.2)" against "-3.2" passes; a missing number fails; two reference numbers need both; a 2% difference fails. Prove they fail, then implement in `scoring35.py` (or `numbers35.py`). Verify: the tests pass.
- [ ] 13.7 Search stage with the reranker router. Write a failing test with a stub router: a reranker-on search stage loads the embedder and the reranker once each, never unloads either between queries, and records both model identities in the trace. Write a second failing test: when a reranker-on query returns results with `_reranked` false or a `last_failure_reason`, the stage saves no row for it, stops with a setup error that names the query and the reason, and writes no done-marker; `--resume` sends that query again. Prove they fail, then implement. Verify: the tests pass.

## 14. Answer budget, selection rule and factorial analysis (redesign, 2026-11-12; design D30, D31)

- [ ] 14.1 Answer context budget, one round (design D30 revision). Write failing tests: `settings_values` of every answer setup holds `answer.context_window` 131072 and `answer.max_rounds` 1; for each chunk size, the largest evidence set (10 passages at the level, 2,048-token fixture of about 9,200 characters each) synthesises through a recording stub seam with exactly one completion call, no context overflow and no truncation; the test fails and names the setup when a second call happens (prove this with `max_rounds` 4 and `context_window` 8192). Prove they fail on today's settings, then set the values. Verify: the tests pass for all three chunk sizes.
- [ ] 14.1a Record the answer model's context length. Write a failing test for a `context35.py` check that reads `context_length` of `deepseek/deepseek-v4.1-flash-1017` from a stubbed OpenRouter models reply and refuses below 65,536 tokens. Prove it fails, then implement. Run it once live in the test pod session (task 9.2). Verify: the test passes and `protocol.md` section 0.5 records the value and the date.
- [ ] 14.2 Write failing tests that each answer row records `completion_calls`, the evidence characters, and the truncated passages and characters dropped, computed with OMRS's own `_fit_and_measure` on the same rows and settings. Prove they fail, then implement in `answers35.py`. Verify: the tests pass, and a row with cut evidence is still saved.
- [ ] 14.3 Selection rule (`select35.py`, design D31). Write failing tests on fixture scores: a gap of exactly 0.01 picks the smaller size; a gap of 0.011 picks the best; equal scores pick the smaller size; the pooled score is the plain mean of the FinanceBench, FreshStack and BioASQ dataset means (not question-weighted; amendment A3); a fixture that changes only the Legal RAG Bench scores changes neither the selected embedder nor the reranker size nor the cell; the four-factor step picks the cell in tie order reranker off, hybrid off, lowest index cost, smaller chunk size; the reranker size is chosen at the chosen embedder on reranker-on setups only; a missing setup stops and names it; `selection.json` lists every pooled score. Prove they fail, then implement. Verify: the tests pass, and the answer stage refuses to start without `selection.json`.
- [ ] 14.5 Ragas `AnswerCorrectness` (design D33). Write failing tests with a stub LLM and stub embeddings: the `ragas` stage scores five metrics, `AnswerCorrectness` gets the question, the answer and the dataset's reference answer (never the contexts), uses the frozen judge and the local 4B embedder, and records the weights; an answer without a reference records "not judged" and sends no call; resume skips saved rows. Prove they fail, then implement in `ragas35.py` with Ragas 0.4.3. Verify: the tests pass, and the version check still refuses another Ragas version.
- [ ] 14.6 Correctness hand-label check (design D33). Write failing tests for `correct35.py`: `sample` with seed 20261113 gives the same 100 answers twice, 25 per dataset and even over chunk sizes, with no Ragas score in the output; the labelling page shows the question, the reference and the answer and saves a JSON file; `agree` binarises at 0.5, gives `cohen_kappa` per dataset and pooled, and marks correctness exploratory below a pooled kappa of 0.60. Prove they fail, then implement. Then, after the main run, L1 labels the sample and L2 labels 30% of it (A2, task 15.8). Verify: the tests pass, `protocol.md` holds the threshold and the kappa rule in a commit before labelling, and then the kappa result (Exp 35 task 4A.4a).
- [ ] 14.4 Factorial analysis (`factorial35.py`, design D31; A2c: H6 on FinanceBench uses `evidence_recall_20k` with both page rules as sensitivity and their sign agreement reported; H8 uses all questions, descriptive headlines half B). Write failing tests on a fixture with a planted embedder effect: only H1's contrasts count; Holm runs across every H1 to H8 contrast within one dataset (A2); a significant wrong-sign contrast does not count; H4 holds only when both of its contrasts count; H6 is tested on FinanceBench and FreshStack only (A2), and BioASQ chunk-size rows carry `sanity_check: true`; H8 averages the 3 runs per question first; Legal rows carry `exploratory: true`. Prove they fail, then implement with the existing statistics functions only. Verify: the tests pass, and `git diff` shows no new function in `experiments/_lib/stats.py` or `stats_d6.py` other than `cohen_kappa` (task 8.8).

## 15. Methods-review fixes (pre-freeze amendment A2, 2026-11-13; design D35)

Each test is proved to fail on the current code before the fix.

- [ ] 15.1 Unit scorer (B1). Write failing tests in `tests/test_experiment35_scoring.py`:
  - 100 ranked chunks where chunks 1 to 3 share one FreshStack document give that document rank 1 once, and the 10-unit list reaches past chunk 10;
  - the same gold set scores the same nDCG@10 whether the chunks are 512 or 2,048 tokens when the unit order is the same (the bias case of `scoring35.py:39-51` fails this today);
  - a FinanceBench chunk spanning pages 41 and 42 with gold page 42 counts for page 41 (first page); the "any page" sensitivity column counts it for 42;
  - fewer than 10 distinct units in 100 chunks scores the short list, missing ranks as misses;
  - `evidence_recall_20k` takes chunks in rank order until their real Qwen3 token total reaches 20,480 (the chunk that crosses the limit is kept whole, nothing after it), as in task 15.14; a test with short chunks proves it does not count by chunk number.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.2 Depth 100. Write failing tests: every search stage saves 100 chunks per question; at depth 100 every reranker setup reranks a pool of exactly 100 (the harness passes `fetch_k=100`; without it `policy.py:63-67` gives 300, which the test must show failing first); a reranker-on search returns the whole reranked pool (100) in order; the answer stage takes its 10 (or 40 or 20) chunks from the head of that list. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.3 Token-matched answer setups (M5, revised by A2c N2). Write failing tests: the answer setup table has 15 setups (A3): the 12 crossed setups on 10 chunks each, plus `c512-t20k`, `c1024-t20k` and `c2048-t20k` at the chosen sizes with reranker on and hybrid on; the evidence of the three `-t20k` setups is cut by real Qwen3 tokens with the rule of task 15.14, while the `c2048` x 10 factorial cell keeps its 10-chunk evidence (a test with short fixture chunks proves `c2048` x 10 still sends 10 chunks and `c2048-t20k` sends more); the cost line of D35 (about +$40, ceiling $975) is checked in the test pod budget sum; with one answer round (task 14.1) the largest 40-chunk set still fits. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.4 Closed-book stage (M6). Write failing tests: `--stage closedbook` sends no search call, uses the frozen answer settings with an empty evidence list and a fixed prompt, writes one row per question for all four datasets, runs `AnswerCorrectness` and the number match, and resumes without repeat calls. Then a report test: correctness split by retrieval hit or miss beside closed-book correctness. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.5 Split halves (M3). Write failing tests: `split35.py` with seed 20261115 gives the same halves twice, splits each dataset about evenly, and `select35.py` reads half A only (a planted half-B effect does not change the choice). Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.6 Mixed model (M2; A2c N4). Tests must also show: each planned contrast's p-value comes from `GEE` (same mean model, Gaussian, exchangeable working correlation) with cluster-robust errors by question, by document on FinanceBench; the MixedLM gives the estimates; Holm runs on the GEE p-values; a fixture with unequal error variance across cells keeps the GEE type I error near 0.05 over 200 simulations. Add `statsmodels` with `uv add --group stats statsmodels`, and add `{include-group = "stats"}` to the `dev` group (decided by the operator, 2026-11-13: a dependency group like `ragas`, kept out of the app install). Write a test that `uv export --no-dev --no-group stats` lists no `statsmodels`. Write failing tests for `experiments/_lib/stats_mixed.py` on a simulated dataset with a known embedder effect and a question random effect: the fitted contrast is within its standard error of the truth; contrasts for H1 to H7 come out with p values that `holm` adjusts across all contrasts of one dataset; the cross-dataset rule gives "holds" at 2 of 3 confirmatory datasets and ignores Legal; H6 needs both FinanceBench and FreshStack. Prove they fail, then implement. Verify: the tests pass, `uv.lock` pins the version, and `tests/test_dependency_floors.py` passes.
- [ ] 15.7 Grouped bootstrap for FinanceBench (M2). Write a failing test that `factorial35.py` passes `groups=doc_name` to `paired_bootstrap` for FinanceBench and no groups elsewhere. Prove it fails, then implement. Verify: the test passes.
- [ ] 15.8 Labelling for two labellers (M4). Extend the page of task 8.4 to three sets (claim kinds, faithfulness verdicts, correctness) with a labeller choice `L1` or `L2` and no name field. Write failing tests for `labels35.py`: seeds 20261112, 20261116 and 20261113 give the stated sizes (100, 200, 100) and strata (dataset; dataset and chunk size; dataset); the L2 subset is 30% of each set with seed plus 1; no judge score or verdict reaches the page; kappa per checker, per dataset and L1 against L2 comes with bootstrap 95% intervals; a "can't tell" after discussion leaves the kappa against the judge and is counted. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.9 Hosted-call provenance (M7). Write failing tests: each answer, Ragas, GLM-5.3 and classifier row records `model_returned` and `provider_returned` from the stubbed reply; the join counts rows whose returned model differs from the requested one per role. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.10 Reranker rank check (M8). Write failing tests for `rerank_check35.py`: 200 pairs drawn with seed 20261117 are the same twice; Spearman below 0.95 marks the file "not pinned". Prove they fail, then implement. Run it on the test pod for each size (task 9.2 step 2a). Verify: the tests pass and `protocol.md` lists the correlation per file.
- [ ] 15.11 MDE from data (M1). Write `mde35.py` on saved files only: per dataset and contrast, the SD of per-question paired differences from Experiment 22 per-query rows (FreshStack) and the smoke and test-pod rows (all four datasets), and `min_detectable_effect` at alpha 0.05 / number of contrasts per dataset, power 0.80; plus the H7 difference-of-differences. Write failing tests on a fixture first. Verify: the tests pass and `protocol.md` section 0.10 holds the table with its sources before the freeze.
- [ ] 15.12 Oracle contexts (design D36; A2c caps). Write failing tests for `oracle35.py` on fixtures of all four datasets: every oracle context is capped at 20,480 Qwen3 tokens with truncation recorded (FinanceBench and BioASQ too); Legal gives the one gold passage; FinanceBench gives the gold page text(s) from the read PDF pages; BioASQ gives the gold corpus passages by relevant passage id; FreshStack gives the gold documents in qrels order, capped at 20,480 Qwen3 tokens, and records the truncated documents and tokens dropped; a missing gold unit stops with a setup error naming it; no search call is sent. Prove they fail, then implement.
- [ ] 15.13 Oracle stage. Write failing tests: `--stage oracle` runs once (run 1), uses the frozen answer prompt and settings with the oracle evidence, and feeds the judge, `ragas` (`AnswerCorrectness`) and number-match stages; the report puts closed-book (floor) and oracle (ceiling) beside the RAG setups, marked descriptive with the no-distractor caveat. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.14 Equal evidence by real tokens (A2c N2). Write failing tests for `evidence_by_tokens`: chunks are taken in rank order while the running Qwen3 token total before a chunk is below 20,480; the chunk that crosses is included whole and no later one; a list of short chunks fills to the budget instead of stopping at a fixed count; `evidence_recall_20k` uses this cut; the token counts come from the pinned tokenizer. Prove they fail on the chunk-count rule, then implement. Verify: the tests pass.
- [ ] 15.15 One round for closed-book and oracle (A2c). Extend the task 14.1 test: the largest oracle context of each dataset and every closed-book prompt synthesise in exactly one completion call. Prove it fails before the caps of task 15.12, then pass it. Verify: the test passes.
- [ ] 15.16 Floor, ceiling and the miss cross-table (A2c). Write failing report tests: floor and ceiling rows are marked single-run beside 3-run averages; a per-question cross-table on retrieval misses counts closed-book correct or not against RAG correct or not, per dataset. Prove they fail, then implement. Verify: the tests pass.

