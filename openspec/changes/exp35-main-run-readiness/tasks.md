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
  - a result finished ahead of an unfinished item is in `<stage>.pending.jsonl` at once, flushed and fsynced before it counts as saved;
  - after a simulated stop, a resume commits pending results in order and asks for calls only for items with neither a row nor a pending result;
  - the done-marker is written after the last commit, and the pending file is then removed;
  - the stage writes and fsyncs a dispatch record (`<stage>.dispatch.jsonl`, item id) before each paid call; a stub stopped after its call returned and before the pending write has a dispatch record and no result, so it is called again once on resume, and the stage trace counts one resent call (`resent_calls` 1); a stub whose result reached the pending file is not called again, and its `resent_calls` stays 0; no resend depends on the answer content.

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
  - missing outcomes follow pre-registration section 12 (A4): every question stays in the denominator; faithfulness per question and setup is the mean over runs with at least one factual claim; a question enters a faithfulness row only when every cell the row uses has a value (complete cases), and the excluded count is printed per setup and row; two sensitivity tables keep every question, with no-claim answers scored 1 and scored 0; the refusal rate per setup is reported as a co-outcome;
  - an answer still missing when its run closes scores 0 for correctness and number match and counts as an answer with no factual claim; a Ragas or checker row still unjudged when its run closes leaves that row's complete cases, is counted, and a sensitivity table scores it 0.

  Prove they fail, then implement with `experiments/_lib/stats_d6.py` (`wilson`, `paired_bootstrap` for the descriptive intervals). Verify: the tests pass.

## 9. Image pin and pre-freeze test pod session (before G7)

- [ ] 9.1 Resolve the digest of `runpod/base:1.6.0-cuda1281-ubuntu2404` and record it before the freeze. Record `runpod/base@sha256:<digest>` in `protocol.md` section 7 and in the `plan.json` `runtime` block. Make the Mac pod-creation script pass that one value as the pod image and as `EXP35_POD_IMAGE`. No such script exists in the repository today. If the operator keeps it outside the repository, record its path and the line that sets the image in `protocol.md`. Verify: the digest read from the registry twice gives the same value, and a dry run of pod creation shows the same pinned value for the image and the variable.
- [ ] 9.2 Run the pre-freeze test pod session (design D24) after groups 0 to 8 and 12 to 14 are merged and their tests pass. Quote the pod price and the expected paid cost (about 6 h, about $5 of pod time plus a few dollars of hosted calls) and wait for the operator's go before creating the pod. Use the standard RTX 4090 pod with the pinned image from task 9.1, its own smoke folder and its own small indexes (`--limit`, `--corpus-sample`); never the main output folder.
  1. End to end, as run 1: ingest, `seal`, search (with a reranker-on and a hybrid-on setup), parallel answers, `clef_flash`, `chat`, `ragas`, `claimkinds`, then `join35.py --smoke --runs 1`. Run the rebuild check once on a toy rebuild of one small index.
  2. FreshStack recheck: `--qids 77536364,77762811` through answer and the two judges in every answer-setup shape (each chunk size, reranker on and off, hybrid on and off). Pass rule: every `answer-summary.json` has `failed` 0 and every judge summary has `errors` 0.
  2a. Reranker files (design D24 revision, item 1): for each Qwen3-Reranker GGUF candidate, a relevant pair scores near 1 and an irrelevant pair near 0, and the ranking of 20 query-passage sets matches the model card's transformers recipe. Record the result per file.
  2b. Reranker throughput at 0.6B, 4B and 8B on 100-candidate pools at 512-, 1,024- and 2,048-token passages; the 8B embedder and the 8B reranker loaded together (peak VRAM, any swap); index build time per chunk size on a fixed slice of each corpus for each embedder.
  3. Calibration: answers at 16, `chat` at 4, Ragas at 16, `claimkinds` at 16. Record per role the 429 and 402 counts, the waits, the stops and the calls per minute. Halve a value that hit a rate-limit stop and repeat that role once. Check that each answer's evidence chunk IDs equal the same run's search IDs. Measure wall seconds per answer per stage and the reported `cost_usd` per answer.
  4. The first budget check (design D23 revision): measured build hours per chunk size times 9 indexes, plus the search stage from the measured reranker throughput, plus three replicate pods at the measured hours, all times the pod price, plus the hosted cost per answer times 41,760, plus the full-corpus FreshStack builds from task 16.2, the two closed-book runs, the oracle run, the length-controlled check and the pilot. When the projection reaches the $975 ceiling, apply the results-blind drop order of design D38 (pre-registration section 17) in order and record each step with the projection that triggered it; no confirmatory item is dropped by choice.
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
  - the order of work of pre-registration section 14.2 (A4): on the Mac, score half A only of the 72 search setups, run the selection rule (`select35.py`) and write `selection.json`; time-stamp the configuration hash with a file upload to the registered OSF project (mechanism: open item O1, task 16.23); only then score half B and start the replicate pods; the scorer refuses a half-B score while the time-stamp record is missing (task 16.17);
  - the budget re-check after the search stage, with the real pod cost so far and the measured rates; when the projection reaches the ceiling, apply the results-blind drop order of design D38 and record each step; no confirmatory item is dropped by choice;
  - the three replicate pods with `--run 1`, `2` and `3`, `--local-dir` on the container disk, and their own checkouts; each pod runs answer (with its own retrieval), the two judges, `ragas` and `claimkinds` for the 15 answer setups on its own run, one stage at a time, with the budget read at each stage end;
  - the expected pod hours from design D22 and D32, as measured by tasks 9.2 and 9.3;
  - the copy-back without `lancedb/`;
  - on the Mac, steps on saved files only: `join35.py`, determinism, the refusal report and statistics;
  - stopping each pod as soon as its work is copied.

  Verify: every command in the procedure runs with `--dry-run` or `--help` as written.
- [ ] 10.2 Write the budget into `preregistration.md` section 17 (A4; it replaces `protocol.md` section 0.8, Exp 35 task 1.11 and the $250 cap of the first 2026-11-12 decision): the estimate of design D38 (about $730, from the D23 figures plus the A4 items) updated with the measured values of tasks 9.2, 9.3 and 16.2, and the ceiling of $975, pods and hosted calls together. State the three checks (design D23): before the freeze, on the index pods after the search stage, and at each stage end during the replicate pods. Each projection uses billing and measured rates only, never scores. State the results-blind drop order of design D38. Set the OpenRouter key's credit limit to the hosted share of the ceiling. Verify: `preregistration.md` states the estimate, the ceiling, the checks, the drop order and the date, and Exp 35 tasks 1.11 and 4A.5 are ticked with a pointer to it.
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

Group 11 runs last, after groups 12 to 16 below (the code tasks of group 16; its pre-freeze tasks close before G7).

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
- [ ] 13.5 FreshStack 203 queries on the full public corpus (amendment A4, 2026-11-14; pre-registration section 4; design D38). Write failing tests: the loader drops the 20 continuity queries; the corpus is the full `freshstack/corpus-oct-2024` config `langchain` at the pinned revision (49,514 documents on the real data; a fixture stands in for tests), with no `continuity/` file, no overlay runbook and no subset or distractor sampling; `datasets35.py` has no `_FS_OVERLAY` or `_FS_OVERLAY_ID` reference and no expected hash for the overlay; the loader refuses a corpus whose revision or row count differs from the pin; questions `77536364` and `77762811` stay. Prove they fail, then remove the overlay constants, its hash entry, its id mapping and the `continuity/*.md` glob, and add the revision and row-count check. Verify: the tests pass, the loader reports 203 queries, and the revision, row count and corpus tree hash from task 16.1 (P1) are in `plan.json`.
- [ ] 13.5a BioASQ passages as `.md` (operator decision, 2026-11-13). Write failing tests: `datasets35.py` writes `<id>.md` (not `.txt`), escapes a leading `#` on any line, and maps gold ids without the suffix. Prove they fail, then implement. Verify: the tests pass.
- [ ] 13.5b Qwen3 token counts on all four datasets. Write a failing test that ingests a small fixture of FinanceBench (Markdown PDF text), FreshStack, BioASQ and Legal at 512, 1,024 and 2,048 tokens and asserts: every chunk has at most the level's Qwen3 token count (pinned tokenizer revision); every dataset goes through the model-token-aware Markdown path; the cl100k counter is never called (patched to raise). Prove it fails on the `.txt` passages, then pass it after 13.4 and 13.5a. Verify: the test passes.
- [ ] 13.6 FinanceBench number match (design D29). Write failing tests with known pairs: "$1,577 million" against "$1.58 billion" passes; "12.5%" against "12.5 percent" passes; "(3.2)" against "-3.2" passes; a missing number fails; two reference numbers need both; a 2% difference fails. Prove they fail, then implement in `scoring35.py` (or `numbers35.py`). Verify: the tests pass.
- [ ] 13.7 Search stage with the reranker router. Write a failing test with a stub router: a reranker-on search stage loads the embedder and the reranker once each, never unloads either between queries, and records both model identities in the trace. Write a second failing test: when a reranker-on query returns results with `_reranked` false or a `last_failure_reason`, the stage saves no row for it, stops with a setup error that names the query and the reason, and writes no done-marker; `--resume` sends that query again. Write a third failing test: the same stop happens in a reranker-on answer setup's own retrieval, and no answer row is written from un-reranked rows. Prove they fail, then implement. Verify: the tests pass.

## 14. Answer budget, selection rule and factorial analysis (redesign, 2026-11-12; design D30, D31)

- [ ] 14.1 Answer context budget, one round (design D30 revision). Write failing tests: `settings_values` of every answer setup holds `answer.context_window` 131072 and `answer.max_rounds` 1; for each chunk size, the largest evidence set (10 passages at the level, 2,048-token fixture of about 9,200 characters each) synthesises through a recording stub seam with exactly one completion call, no context overflow and no truncation; the test fails and names the setup when a second call happens (prove this with `max_rounds` 4 and `context_window` 8192). Prove they fail on today's settings, then set the values. Verify: the tests pass for all three chunk sizes.
- [ ] 14.1a Record the answer model's context length. Write a failing test for a `context35.py` check that reads `context_length` of `deepseek/deepseek-v4.1-flash-1017` from a stubbed OpenRouter models reply and refuses below 65,536 tokens. Prove it fails, then implement. Run it once live in the test pod session (task 9.2). Verify: the test passes and `protocol.md` section 0.5 records the value and the date.
- [ ] 14.2 Write failing tests that each answer row records `completion_calls`, the evidence characters, and the truncated passages and characters dropped, computed with OMRS's own `_fit_and_measure` on the same rows and settings. Prove they fail, then implement in `answers35.py`. Verify: the tests pass, and a row with cut evidence is still saved.
- [ ] 14.3 Selection rule (`select35.py`, design D31). Write failing tests on fixture scores: a gap of exactly 0.01 picks the smaller size; a gap of 0.011 picks the best; equal scores pick the smaller size; the pooled score is the plain mean of the FinanceBench, FreshStack and BioASQ dataset means (not question-weighted; amendment A3); a fixture that changes only the Legal RAG Bench scores changes neither the selected embedder nor the reranker size nor the cell; the four-factor step picks the cell in tie order reranker off, hybrid off, lowest index cost, smaller chunk size; the reranker size is chosen at the chosen embedder on reranker-on setups only; a missing setup stops and names it; `selection.json` lists every pooled score, both chosen sizes, the A3 cell and the configuration hash. Then (A4, pre-registration section 14.1) tests that: index cost is the number of chunks times the embedding dimension, summed over the three core datasets, read from the sealed indexes with no score; the configuration hash is the SHA-256 of the canonical JSON (keys sorted, no spaces, UTF-8) of the selected cell's resolved settings with the SHA-256 of `halves.json` as one field, and the same inputs give the same hash twice; the any-page sensitivity repeats step 3 with any-page nDCG@10 on FinanceBench, records whether the cell changes, and never changes the registered cell. Prove they fail, then implement. Verify: the tests pass, and the answer stage refuses to start without `selection.json`.
- [ ] 14.5 Ragas `AnswerCorrectness` (design D33). Write failing tests with a stub LLM and stub embeddings: the `ragas` stage scores five metrics, `AnswerCorrectness` gets the question, the answer and the dataset's reference answer (never the contexts), uses the frozen judge and the local 4B embedder, and records the weights; an answer without a reference records "not judged" and sends no call; resume skips saved rows. Prove they fail, then implement in `ragas35.py` with Ragas 0.4.3. Verify: the tests pass, and the version check still refuses another Ragas version.
- [ ] 14.6 Correctness gate per core dataset (design D33 as revised by D38; pre-registration section 11.2). Write failing tests for `correct35.py`: `sample` with seed 20261113 gives the same 200 answers twice, 50 questions per dataset (the three core datasets and Legal) from half B, each with the run-1 answer of an answer setup the seed picks uniformly, with no Ragas score in the output; the labelling page shows the question, the reference and the answer and saves a JSON file; `agree` cuts the Ragas score at 0.5 and gives per core dataset `cohen_kappa` with a percentile bootstrap 95% interval (10,000 resamples by question, seed 20261127), computed twice with "can't tell" scored as correct and as not correct; the gate passes on a dataset only when both computations give a point estimate of at least 0.60 and a lower bound of at least 0.40; the continuous score's AUC against the human label must have a lower 95% bound above 0.5 (same bootstrap, seed 20261128); prevalence, raw agreement and PABAK sit beside kappa; Legal is reported with no gate; a failed gate marks rows 14, 15, 18 and 19 "not testable" on that dataset (p = 1, task 15.7); no pooled kappa decides anything. Prove they fail, then implement. Then, after the main run, L1 labels the sample and L2 labels 30% of it (task 15.8). Verify: the tests pass, `protocol.md` holds the gate in a commit before labelling, and the gate is decided before any H8a or H8b contrast result is computed (C35 task 4A.4a).
- [ ] 14.4 Factorial analysis (`factorial35.py`, design D31 and D38; pre-registration sections 7, 8 and 14.3). H6 and H7 on FinanceBench use `evidence_recall_20k` (any-page credit), with nDCG@10 under both page rules as sensitivity and their sign agreement per row reported; H8a and H8b use all questions; the RQ1 headline is the A3 cell on half B. Write failing tests on a fixture with a planted embedder effect: only H1's rows count; Holm runs within one dataset over the fixed family of task 15.7; a significant wrong-sign row does not count; "holds" follows the per-hypothesis rule of section 7 (H1 in full when both steps hold, in part when one does; H2, H3 and H5 on at least 2 of 3 core datasets; H4 per dataset when both rows count, overall on at least 2 of 3; H6, H7, H8a and H8b on both FinanceBench and FreshStack, H8a and H8b per outcome (O6); a two-sided hypothesis holds only when the same row counts with the same sign on each dataset its rule needs, and opposite signs are reported as a dataset-dependent effect); H8a rows use the 12 crossed setups and H8b rows the 3 `-t20k` setups; BioASQ rows 9 to 19 carry `sanity_check: true`; answer scores average the 3 runs per question first; Legal rows carry `exploratory: true`; the RQ1 retrieval headline is the A3 cell's nDCG@10 on half B per core dataset with a 95% interval, and the 72-setup table on all questions is marked descriptive; the search-cost figure uses the exact expected-maximum estimator (adapted from Dodge et al. 2019, drawn without replacement) on pooled half-A scores sorted in ascending order, one curve over the 12 A3 cells and one over the 72 setups, and a RAGFlow curve only if the matched search ran. Prove they fail, then implement with `stats_cluster.py` (task 15.6) and the existing functions. Verify: the tests pass, and `git diff` shows no new function in `experiments/_lib/stats.py` or `stats_d6.py` other than `cohen_kappa` (task 8.8).

## 15. Methods-review fixes (pre-freeze amendment A2, 2026-11-13; design D35)

Each test is proved to fail on the current code before the fix.

- [ ] 15.1 Unit scorer (B1). Write failing tests in `tests/test_experiment35_scoring.py`:
  - 100 ranked chunks where chunks 1 to 3 share one FreshStack document give that document rank 1 once, and the 10-unit list reaches past chunk 10;
  - the same gold set scores the same nDCG@10 whether the chunks are 512 or 2,048 tokens when the unit order is the same (the bias case of `scoring35.py:39-51` fails this today);
  - for nDCG@10, Recall@10, MRR@10 and hit@page, a FinanceBench chunk spanning pages 41 and 42 with gold page 42 counts for page 41 (first page, primary); the "any page" sensitivity column counts it for 42;
  - nDCG@10, Recall@10 and MRR@10 follow the formulas of pre-registration section 6 (trec_eval convention, ideal DCG over min(R_q, 10) gold units, plain mean over questions); a known-answer fixture with 12 gold units checks the cap;
  - fewer than 10 distinct units in 100 chunks scores the short list, missing ranks as misses;
  - `evidence_recall_20k` takes chunks in rank order while the Qwen3 token total before a chunk is below 20,480 (the chunk that crosses the limit is truncated at the limit, nothing after it), as in task 15.14; a test with short chunks proves it does not count by chunk number;
  - `evidence_recall_20k` uses any-page credit on FinanceBench (pre-registration section 6): a whole chunk covers every gold page it overlaps, and the truncated crossing chunk covers only its first page; first-page credit is a separate sensitivity column; on FreshStack, BioASQ and Legal a chunk, whole or truncated, covers its one unit.

  Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.2 Depth 100. Write failing tests: every search stage saves 100 chunks per question; at depth 100 every reranker setup reranks a pool of exactly 100 (the harness passes `fetch_k=100`; without it `policy.py:63-67` gives 300, which the test must show failing first); a reranker-on search returns the whole reranked pool (100) in order; the answer stage takes its 10 (or 40 or 20) chunks from the head of that list. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.3 Token-matched answer setups (M5, revised by A2c N2). Write failing tests: the answer setup table has 15 setups (A3): the 12 crossed setups on 10 chunks each, plus `c512-t20k`, `c1024-t20k` and `c2048-t20k` at the chosen sizes with reranker on and hybrid on; the evidence of the three `-t20k` setups is cut by real Qwen3 tokens with the rule of task 15.14, while the `c2048` x 10 factorial cell keeps its 10-chunk evidence (a test with short fixture chunks proves `c2048` x 10 still sends 10 chunks and `c2048-t20k` sends more); the cost line of D35 (about +$40, ceiling $975) is checked in the test pod budget sum; with one answer round (task 14.1) the largest 40-chunk set still fits. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.4 Closed-book stages (M6; A4, pre-registration section 13). Write failing tests: `--stage closedbook` runs two prompts, each once on all 1,160 questions: the own-knowledge prompt (floor) and the main RAG answer prompt with an empty evidence block; neither sends a search call; both use the frozen answer settings, write one row per question for all four datasets, run `AnswerCorrectness` and the number match, and resume without repeat calls. Then report tests: closed-book correctness per dataset beside every correctness table; the per-question cross-table on retrieval misses; and the registered contamination sensitivity, which re-runs rows 14, 15, 18 and 19 on the questions that both closed-book runs answer wrongly (Ragas correctness below 0.5). Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.5 Split halves (M3; A4, pre-registration section 4). Write failing tests: `split35.py` with seed 20261115 gives the same halves twice; FinanceBench is split by document (documents shuffled with the seed, each going with all its questions to the half that has fewer questions so far, ties to A), so no document sits in both halves; FreshStack, BioASQ and Legal are split by question (shuffled, first half rounded up is half A); `halves.json` lists every question ID with its half; `select35.py` reads half A only (a planted half-B effect does not change the choice). Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.6 Clustered analysis (A4 replaces M2 and A2c N4; pre-registration section 9). No MixedLM. Write failing tests for `experiments/_lib/stats_cluster.py` and `factorial35.py`:
  - the per-question contrast score d_qk is the mean over first-level cells minus the mean over second-level cells (equal cell weights), with answer scores averaged over the 3 runs first; the estimate is the plain mean of d_qk; on FreshStack, BioASQ and Legal the decision test is the closed form of PR 9 point 3: variance = (sum of squared residuals) x (n / (n minus 1)) squared / n squared, and the p-value and 95% interval use t on n minus 1 degrees of freedom, computed by our code whatever reference the library reports by default (`statsmodels` GEE results use a normal reference unless told otherwise); the implementation is `statsmodels` `GEE` of d_qk on an intercept (Gaussian, identity link, independence working correlation, clusters = questions, `cov_type="bias_reduced"`); a known-answer test on a fixed fixture checks that the GEE estimate and variance equal the closed form and that the closed form equals the paired t-test variance times n / (n minus 1); if the library does not match, the code uses the closed form and the report states the difference;
  - FinanceBench uses the document-level sign-flip permutation test: the statistic is the question-weighted mean d_qk, each document's sum is flipped at random, 100,000 draws with seed 20261101, p = (1 + draws at least as large in absolute value) / 100,001, and the 95% interval inverts the same test on the same draws;
  - registered sensitivity checks, never decisive: a paired permutation test by question on FreshStack and BioASQ (10,000 shuffles, seed 20261101, `paired_permutation`), and the GEE above with document clusters on FinanceBench; every row where decision and sensitivity disagree on "counts" goes into one table;
  - type I error simulation, now for this method: with no planted effect and unequal error variance across cells, the rejection rate at 0.05 stays near 0.05 over 200 simulations for the GEE (FreshStack-sized data) and for the sign-flip test (84 documents, about 1.8 questions each); a fixture with complete data gives the same estimate as the cell-means contrast of the full-factorial model.
  - Add `statsmodels` in a new `stats` dependency group (decided by the operator, 2026-11-13; not yet in `pyproject.toml` or `uv.lock`), with `{include-group = "stats"}` in the `dev` group; a test checks that `uv export --no-dev --no-group stats` lists no `statsmodels`. Prove they fail, then implement. Verify: the tests pass, `uv.lock` pins the version, and `tests/test_dependency_floors.py` passes.
- [ ] 15.7 Holm families and gated rows (A4, pre-registration sections 7 and 8). Write failing tests for `factorial35.py`: the contrast table holds rows 1 to 19 with the signs and endpoints of section 8; family sizes are fixed at 19 (FinanceBench), 19 (FreshStack) and 8 (BioASQ, rows 1 to 8; O6); BioASQ rows 9 to 19 are sanity checks with unadjusted 95% intervals and no decision; Legal has no family; a row that fails its gate or the differential-error rule stays in its family with p = 1, takes the last Holm rank, and is marked "not testable", so no gate changes a family size; a directional row counts only with Holm p below 0.05 and the predicted sign. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.8 Labelling for two labellers (M4; A4, pre-registration section 11.3). Extend the page of task 8.4 to three sets (claim kinds, faithfulness verdicts, correctness) with a labeller choice `L1` or `L2` and no name field. Write failing tests for `labels35.py`: seeds 20261112, 20261116 and 20261113 give the sizes 100, 450 and 200 (L1: 750 in all) with strata dataset; core dataset and chunk size (150 per chunk size, 50 per core dataset within each, at most one claim per answer, crossed setups only, drawn from answers to all questions in both halves); and dataset (50 questions per dataset, half B only, one run-1 answer of a setup picked uniformly); the L2 subset is 30% of each set with seeds 20261122, 20261123 and 20261124 (225 in all); no score, verdict, setup name or chunk size reaches the page; kappa per checker, per dataset and L1 against L2 comes with percentile bootstrap 95% intervals (10,000 resamples by question; seeds 20261125 and 20261129, PR 16); the disagreement rule makes an unresolved item "can't tell" and counts it. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.9 Hosted-call provenance (M7). Write failing tests: each answer, Ragas, GLM-5.3 and classifier row records `model_returned` and `provider_returned` from the stubbed reply; the join counts rows whose returned model differs from the requested one per role. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.10 Reranker rank check (M8). Write failing tests for `rerank_check35.py`: 200 pairs drawn with seed 20261117 are the same twice; Spearman below 0.95 marks the file "not pinned". Prove they fail, then implement. Run it on the test pod for each size (task 9.2 step 2a). Verify: the tests pass and `protocol.md` lists the correlation per file.
- [ ] 15.11 MDE from the pilot (M1; A4, pre-registration section 10). Write `mde35.py` on saved files only: per core dataset and contrast type, the SD of the per-question contrast scores from the retrieval-only pilot (task 16.5, P5; an adjacent-level contrast uses the extreme-level SD as a stand-in, marked so), and on FinanceBench the design effect of document clustering; MDE = (z at 1 minus alpha/2 plus z at 0.80) x SD / square root of n, with alpha 0.05/19 on FinanceBench and FreshStack and 0.05/8 on BioASQ, and n divided by the design effect on FinanceBench; answer-stage rows use the SD from the smoke and test-pod answer files named in task 16.6 (P6) and are labelled rough; each row is shown against the SESOI (0.02 nDCG@10, open item O2). Experiment 22 values are not used. Write failing tests on a fixture first. Verify: the tests pass and the MDE table of pre-registration section 10 is filled before the freeze.
- [ ] 15.12 Oracle contexts (design D36; A2c caps). Write failing tests for `oracle35.py` on fixtures of all four datasets: every oracle context is capped at 20,480 Qwen3 tokens with truncation recorded (FinanceBench and BioASQ too); Legal gives the one gold passage; FinanceBench gives the gold page text(s) from the read PDF pages; BioASQ gives the gold corpus passages by relevant passage id; FreshStack gives the gold documents in qrels order, capped at 20,480 Qwen3 tokens, and records the truncated documents and tokens dropped; a missing gold unit stops with a setup error naming it; no search call is sent. Prove they fail, then implement.
- [ ] 15.13 Oracle stage. Write failing tests: `--stage oracle` runs once (run 1), uses the frozen answer prompt and settings with the oracle evidence, and feeds the judge, `ragas` (`AnswerCorrectness`) and number-match stages; the report puts closed-book (floor) and oracle (ceiling) beside the RAG setups, marked descriptive with the no-distractor caveat. Prove they fail, then implement. Verify: the tests pass.
- [ ] 15.14 Equal evidence by real tokens (A2c N2; A4 page credit). Write failing tests for `evidence_by_tokens`: chunks are taken in rank order while the running Qwen3 token total before a chunk is below 20,480; the chunk that crosses is truncated at 20,480 tokens, the truncation is recorded per question, and no later chunk is taken; a list of short chunks fills to the budget instead of stopping at a fixed count; `evidence_recall_20k` uses this cut with any-page credit on FinanceBench (a whole chunk covers every gold page it overlaps; the truncated chunk covers only its first page) and reports first-page credit as a sensitivity column; the token counts come from the pinned tokenizer. Prove they fail on the chunk-count rule, then implement. Verify: the tests pass.
- [ ] 15.15 One round for closed-book and oracle (A2c). Extend the task 14.1 test: the largest oracle context of each dataset and every closed-book prompt synthesise in exactly one completion call. Prove it fails before the caps of task 15.12, then pass it. Verify: the test passes.
- [ ] 15.16 Floor, ceiling and the miss cross-table (A2c). Write failing report tests: floor and ceiling rows are marked single-run beside 3-run averages; a per-question cross-table on retrieval misses counts closed-book correct or not against RAG correct or not, per dataset. Prove they fail, then implement. Verify: the tests pass.

## 16. Publication-review fixes (pre-freeze amendment A4, 2026-11-14; design D38)

`preregistration.md` governs; "PR n" below means its section n. Tasks 16.1 to 16.16 are the pre-freeze tasks P1 to P16 of PR 23, in the same order. Tasks 16.17 to 16.22 are code. Tasks 16.23 to 16.28 are the user's decisions O1 to O6; record each answer, never guess it. Every task closes before G7.

- [ ] 16.1 P1. FreshStack full corpus. Ask the user to approve the download of `freshstack/corpus-oct-2024`, config `langchain`, at a pinned revision. Then download it into `~/Development/DATA/omrs/` and record the revision, the row count (49,514 expected) and the corpus tree hash in `plan.json` and in the pins table (PR 16). Verify: the loader of task 13.5 accepts the corpus, and its check refuses a changed row count.
- [ ] 16.2 P2. Time one full-corpus FreshStack index build on the chosen GPU type (part of task 9.2 or 9.3 when possible). Update the estimate in PR 17 from the measured time before relying on it. Verify: the compute table and the estimate name the measured hours; the "30 to 40 pod hours" reviewer figure is no longer the basis.
- [ ] 16.3 P3. Check whether the FreshStack nugget labels allow alpha-nDCG@10 with the benchmark's own scorer. If yes, pin the scorer (version or commit) and write failing tests that a FreshStack secondary column holds it, then implement. If no, record "not available" in PR 6. Verify: PR 6 and `plan.json` say which.
- [ ] 16.4 P4. Check, per dataset, whether the qrels list judged non-relevant units. Record the answer. Then write failing report tests: the unjudged share at 10 per setup and dataset; condensed-list nDCG@10 (unjudged units removed) as a sensitivity analysis for H1 to H5 where non-relevant judgements exist; and the statement "neither can be computed" where the qrels hold positives only. Prove they fail, then implement. Verify: the tests pass and PR 21 matches the recorded answer.
- [ ] 16.5 P5. MDE pilot. Fix the pilot cell list before the pilot runs: at most 4 indexes per core dataset, the H7 corner cells, built with the pinned settings and not reused. Project the pilot cost from the P2 timing, add it to the PR 17 estimate and get the user's approval; if declined, apply the PR 10 fallback (assumed SDs 0.15 to 0.25). Draw 40 questions per core dataset from half A with seed 20261118 (after task 16.12). Run retrieval only on the full-corpus indexes, with no hosted call, after a price quote and the user's go. Run `mde35.py` (task 15.11) and fill the MDE table of PR 10. Verify: every pilot question ID is in half A, the cell list has a commit dated before the pilot, the table is filled, and the pilot pod hours are in the compute table.
- [ ] 16.6 P6. Name the smoke and test-pod answer files that feed the H8a and H8b MDE rows, with their SHA-256. Verify: PR 10 names them and marks those rows rough.
- [ ] 16.7 P7. Restate the checker 2-point tolerance against the H8a and H8b faithfulness MDE: the bar stays only if it is at most half that MDE. Verify: PR 11.1 and `protocol.md` section 4.4 give the restated rule; the "about 4 points" figure is not used.
- [ ] 16.8 P8. Write one label guideline per set (claim kinds, faithfulness, correctness, Part 2 correctness), with worked examples drawn from outside every sample. Faithfulness follows the LLM-AggreFact task definition. Fix each guideline before its first label. Verify: the guidelines are committed before any label, and no worked example is in a sample (a test of `labels35.py` checks the IDs).
- [ ] 16.9 P9. Ask the user to confirm or change the seeds 20261118 (pilot), 20261119 (length-controlled check) and 20261121 to 20261135 (seeds table of PR 16), and the length-controlled sample size of 300. Seed 20261120 (audit) is used only if O3 (task 16.25) is yes; confirm it then. Verify: PR 16 and `plan.json` hold the confirmed values.
- [ ] 16.10 P10. Record in `plan.json`: the tokenizer revision; the answer-model host, reasoning mode, output cap and context length (task 14.1a); the Ragas judge and classifier host and settings; the GLM-5.3 settings. Verify: each "Missing: P10" cell of PR 16 points to a `plan.json` key.
- [ ] 16.11 P11. Record in `plan.json`: the query instruction (empty string), the reranker instruction text, and the hybrid settings (RRF constant, per-side fusion depth, BM25 tokeniser and parameters). Write a failing test that the run record of a search stage holds the same values, then implement. Verify: the test passes.
- [ ] 16.12 P12. Run `split35.py` (task 15.5), write `halves.json`, record its SHA-256 in `plan.json`, and list every smoke and pre-freeze question ID with its half in the existing-data table (PR 5). Verify: the hash in `plan.json` equals the file, and every listed ID has a half.
- [ ] 16.13 P13. Record the SHA-256 of the prompt templates: answer, both closed-book prompts, oracle, classifier. Verify: `plan.json` holds them and a test recomputes each one.
- [ ] 16.14 P14. Set the `evidence_recall_20k` tolerance on another back end, with its reason, in `plan.json` `runtime.tolerance`. Verify: PR 15 names it.
- [ ] 16.15 P15. Check that no file still names `openai/gpt-6.1-terra` as a cross-check judge (A4 removed it from `plan.json`). This change never planned it. The `experiment-35-full-document-rag-benchmark` design marks its cross-check text as removed by A4. Verify: a search for `gpt-6.1-terra` finds it only in history text.
- [ ] 16.16 P16. Part 2 and E1 inputs (readiness flow group 7): own estimates and ceilings for Part 2 and for E1; RAGFlow defaults read from the pinned release, not main-branch documentation; the three-column settings table; the matched RAGFlow cell list fixed before FLOW step 7.2; the cost measured at FLOW step 7.2 and the decision at FLOW step 7.2a (at most $50 projected pod cost), recorded before any half-B score exists. Verify: the Part 2 protocol holds each item and FLOW steps 7.1, 7.2 and 7.2a are done.
- [ ] 16.17 Half-B guard (PR 14.2). Write failing tests: the scorer refuses any half-B score while `selection.json` or the OSF time-stamp record (upload time and file hash, task 16.23) is missing, and names both; the replicate pods' first stage refuses to start under the same condition; half-A scoring needs neither. Prove they fail, then implement. Verify: the tests pass.
- [ ] 16.18 Faithfulness gate and differential-error rule (PR 11.2). Write failing tests for `labels35.py`: per checker, kappa against the human label on the 450-claim sample (drawn from answers to all questions, both halves), with "can't tell" as not supported (also reported with those items left out), passes at a point estimate of at least 0.60 and a lower bound of at least 0.40 (percentile bootstrap by question, seed 20261125); a failed Clef-Flash gate marks its results not validated and changes no row; specificity per chunk size, and when the 95% interval of the GLM-5.3 2,048 minus 512 difference (seed 20261126) excludes zero in either direction, rows 12, 13, 16 and 17 become "not testable" (p = 1, task 15.7); sensitivity per chunk size is reported; the gate file records its time and the analysis refuses to compute an H8a or H8b row before it exists. Prove they fail, then implement. Verify: the tests pass.
- [ ] 16.19 Length-controlled check (PR 11.2). Write failing tests for a `lengthcheck` stage: 300 claims from `c2048` crossed answers with seed 20261119; each cited chunk split into consecutive 512-token windows, the window that shares the most distinct lower-case claim words kept (ties to the earlier window); GLM-5.3 and Clef-Flash judge the claim again; the report gives the verdict change rate with a Wilson interval; no gate. Prove they fail, then implement. Verify: the tests pass.
- [ ] 16.20 Report items (PR 21). Write failing report tests: the realised chunk-length distribution per chunk-size level and dataset; one sensitivity table set (clustered method against sensitivity check, FinanceBench page rules, missing-outcome bounds, closed-book subset, length-controlled check, A3 cell under any-page credit); the compute table (GPU type, pod hours per stage with every pre-freeze pod, hosted tokens and cost per role, energy estimate, `resent_calls`, error rows per stage and role, every `out_of_credit` stop); the returned model ID and provider per hosted call with the count of differences; every row with SESOI and MDE lines and "not testable" marks. Prove they fail, then implement. Verify: the tests pass.
- [ ] 16.21 Release kit (PR 19). Write failing tests for a re-judge script that rebuilds evidence text from the pinned dataset revisions and the released unit and chunk IDs, on a fixture; and for an export that writes ranked lists in TREC run format, never corpus text. Prove they fail, then implement. Verify: the tests pass, and the release table of PR 19 names each artefact and its licence.
- [ ] 16.22 Optional `e8b-c2048` rebuild check (PR 15). Run it on FinanceBench only when the cost projection after the search stage is at or below the estimate (a cost-only decision, recorded). Report the share of identical ranked lists and the nDCG@10 change; it is not a gate. Verify: the decision and, if run, the result are in the run record.
- [ ] 16.23 O1 (user decides). The OSF mechanism that time-stamps the A3 configuration hash (proposed: a file upload to the registered project). Record the answer in PR 14.2 and PR 23. Verify: the answer is recorded before G7.
- [ ] 16.24 O2 (user decides). The SESOI value (proposed: 0.02 nDCG@10). Record the answer in PR 10. Verify: recorded before the pilot results are read.
- [ ] 16.25 O3 (user decides). Whether the optional blind relevance audit for H3 and C1 runs (about 300 to 400 L1 labels, seed 20261120, descriptive). Record the answer. If yes, add its sample and page to `labels35.py` with tests first. Verify: the answer is recorded before G7.
- [ ] 16.26 O4 (user decides). L2's name, role and relation to the project. Record it in the run record only, never in public files. Verify: no public file holds the name.
- [ ] 16.27 O5 (user decides). The ethics query to the university and its answer, before the first label. Verify: the answer is recorded before any label.
- [ ] 16.28 O6 (user decides). BioASQ rows 12 to 19 as sanity checks (families 19 / 19 / 8; H8a and H8b on FinanceBench and FreshStack), or the alternative: rows 12 to 19 in the BioASQ family (16 rows) with 2-of-3 for H8. Record the answer in PR 7, 8 and 23. Verify: recorded before G7.
