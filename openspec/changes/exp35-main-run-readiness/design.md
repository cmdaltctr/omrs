# Design

## Context

See proposal.md (Why) for the motivation and specs/ for the requirements. This section gives only the current code facts that shape the approach. Paths below are relative to `experiments/35-full-rag-benchmark-2026-11-01/` unless they start with `experiments/` or `src/`.

**Everything runs one call at a time.**

- The answer stage awaits one answer per question in a plain loop (`stages35.py:260-271`, the call at `:267`).
- The judge stage loops over answers (`stages35.py:329-345`). `run_arms.py:341-343` runs the judges one after another. `verify_claims` awaits one judge call per claim (`src/omrs/core/answer/verify.py:367-371`).
- `run_arms.py` has no concurrency option (`run_arms.py:63-88`). Only `prefreeze/run_glm_chat.py` has `--concurrency` (`:199`), with `asyncio.gather` workers (`:129-165`). Its rows are written in finishing order (`:135`), so it cannot give the frozen order.

**Errors and rate limits.**

- An answer error is kept in the row and the run continues (`stages35.py:268-271`). `--resume` skips every saved row (`stages35.py:259-262`), so an error row is never sent again.
- OMRS turns a generation exception into an error result: status `error`, `answer` null, `failure_stage` `generation` and the text `Generation failed: <type>: <detail>` in `error` (`src/omrs/core/answer/stages.py:171-185`, built by `results.py:134-166`). Nothing in the result marks a rate limit, so a caller can find one only by reading that text. The harness keeps the error row, so a rate-limit reply on an answer becomes a saved error row today. Before D25, the harness had to parse the text; D25 fixes this in OMRS.
- A failed GLM-5.3 (`chat`) call raises `JudgeUnavailable`. The run stops before that answer is saved, and `--resume` retries it (`stages35.py:356-365`; `arms.py:49`).
- The only retries come from the libraries. `llama-index-llms-openai` 0.7.10 retries `RateLimitError` (HTTP 429), connection, timeout and server errors: 3 attempts, random backoff from 1 s to 20 s, stop after 60 s (`llama_index/llms/openai/base.py:112`, `utils.py:350`). It honours `Retry-After` up to 120 s (`utils.py:274`). The `openai` 2.54.0 client retries 429 on its own too. Neither retries HTTP 402.
- OpenRouter answer calls carry `provider: {only, allow_fallbacks: false, require_parameters: true}` (`src/omrs/core/providers/llm/openrouter_hosts.py:163`).

**Stages and layout.**

- `STAGES = ingest, search, answer, determinism` (`arms.py:55`). There is no Ragas stage.
- Ragas exists only in `prefreeze/measure_answers.py` and `prefreeze/ragas_stage.py`. The judge is `openai/gpt-oss-120b` on OpenRouter (`prefreeze/measure_lib.py:23`, built in `prefreeze/measure_live.py:157-192`). One question and one metric run at a time (`prefreeze/ragas_stage.py:313-341`). The recording seam holds shared mutable state (`metric`, `calls`; `ragas_stage.py:85-87`), which `judge_answer` resets per answer (`:326`). `judge_answer` catches every metric exception and records only its type name (`:336-337`).
- `--run 1|2|3` exists (`run_arms.py:69`).
- Layout (`outputs35.py:38-73`): the shared store is `<out>/lancedb` (`:56-59`), index markers are under `<out>/<dataset>/<owner>/index/` (`:48-50`), and outputs are under `<out>/<dataset>/<arm>/run<n>/` (`:52-54`). `<out>/state` is `OMRS_STATE_DIR` (`:61-64`, set at `experiments/_lib/router_env.py:248`). `<out>/config/<dataset>-<arm>-<stage>` holds the scratch `omrs.jsonc` (`:71-73`), and `<out>/work` holds the prepared corpus (`:66-69`).
- `reranker-off` and `hybrid` search the `documents-profile-4b` index (`arms.py:94`, `:96`). The 2026-11-12 redesign replaces this arm table with settings-named setups (D28).

**Redesign of 2026-11-12.** Experiment 35 became a full factorial (pre-freeze amendment A1; Exp 35 change design D0; `protocol.md` section 0): 9 indexes and 72 search setups per dataset on four datasets, then 12 answer setups x 3 runs. Granite Guardian and H-CC are dropped. D27 to D31 hold the new decisions. D13, D20, D22, D23 and D24 carry dated revisions; their older text stays below each revision for history. Where an older line names an arm, `documents-profile-4b`, Granite Guardian, H-CC or the $250 cap, the revision wins.

**Facts that shape the redesign work (checked 2026-11-12).**

- Reranker dispatch: `retrieval.rerank_backend` maps to a registry name in `src/omrs/core/retrieval/backend.py:29-32` (`onnx` to `reranker_onnx`, `torch` to `reranker_torch`). `build_reranker_from_settings` (`backend.py:105-125`) constructs the class with `model_id=settings.retrieval.rerank_model` only. The registry lines are `src/omrs/core/retrieval/registry.py:63-64`. The accepted values live in `src/omrs/config/rules.py:41`.
- Rerank pool: `fetch_k = max(rerank_max_fetch, top_k x rerank_fetch_multiplier)` = max(100, 30) = 100 candidates per query (`src/omrs/core/retrieval/policy.py:63-67`). `similarity_threshold` defaults to 0.0 (`src/omrs/core/retrieval/settings.py:42`), so no reranker score drops a result.
- Router presets accept `pooling: rank` already (`src/omrs/config/llamacpp_preset.py:73`), with `embeddings: true`. The router listens on 18080 in the harness (`experiments/_lib/router_env.py:30-31`), and the harness loads one model at a time (`arms.ROUTER_MODELS_MAX = 1`, `arms.py:45`).
- Chunk size: `split_documents` uses `settings.chunking.markdown_chunk_size` for Markdown text and the `chunk_size` argument otherwise (`src/omrs/core/ingestion/chunker.py:229`). Markdown text is a `.md` file or a reader that declares `text_format == "markdown"` (`chunker.py:148-157`). `pdf_inspector` declares `markdown` (`src/omrs/integrations/pdf/registry.py:159-168`). The plain `SentenceSplitter` (`src/omrs/core/chunking/sentence.py:60-63`) gets no tokenizer, so it uses the LlamaIndex default, tiktoken for `gpt-3.5-turbo` (cl100k). Defaults: `chunk_size` 512, `chunk_overlap` 100, `markdown_chunk_size` 1,024 (`src/omrs/config/defaults.yaml:21-23`).
- Settings reach a stage through the scratch `omrs.jsonc` that `arms.settings_values` writes (`arms.py:149-200`); `router_env.check_resolved` refuses an environment or `.env` value that overrides it.
- Answer budget: `answer.context_window` 8,192 characters per round and `answer.max_rounds` 4 (`src/omrs/core/answer/settings.py:102-103`); the per-round budget widens to fit the evidence into the round bound, up to 262,144 characters (`src/omrs/core/answer/synthesis.py:57`, `:169-189`). Cut evidence carries the marker `[evidence truncated]` (`synthesis.py:70`).
- The router port is fixed at 18080 (`experiments/_lib/router_env.py:30-31`).
- `guard_run` appends a line to `<experiment folder>/output/run-records.jsonl` of the checkout that runs the process (`live35.py:59` with `command=None`; `experiments/_lib/run_guard.py:35-63`).
- Root gotcha 17 says the state folder must be on a local disk.
- The judge row stores the claim index, ordinals, verdict and call record, but no claim text (`stages35.py:346-354`).

**The OMRS native full-text query writes to the store.** The native path calls `ensure_fts_index` (`src/omrs/core/vectordb/lancedb/fts.py:180`). That creates the index when it is absent (`fts.py:75-90`). It calls `refresh_fts_index`, which runs `table.optimize()`, when rows are unindexed (`fts.py:192`, `:101`). D26 fixes this in OMRS.

**The Exp 35 hybrid arm does not take the native path today.** The protocol defines the arm as "Hybrid (BM25 + dense, RRF)" (`protocol.md` section 3). The harness sets no sparse backend, so the default `bm25` applies (`src/omrs/config/defaults.yaml:53`, `src/omrs/core/retrieval/settings.py:87`). The FreshStack rerun store, which ran the hybrid arm, holds no `_indices` folder (`DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/fs-rerun/results/fs-out.tgz`). So three pods would not race to write a full-text index with the current settings. The seal (D8) still checks the store, because a replicate pod must not write it for any reason.

**`Engine.answer` accepts pre-retrieved rows** (`src/omrs/engine.py:273`). Without them, the pipeline retrieves inside the answer call (`src/omrs/core/answer/pipeline.py:251`).

**File sizes.** `stages35.py` has 453 lines, `run_arms.py` 387 and `tests/test_experiment35_run_arms.py` 449. The ceiling is 500 lines.

## Goals / Non-Goals

**Goals:**

- Send hosted calls in parallel with bounded, recorded limits. Keep every output byte-identical to a serial run.
- Never lose or repeat a paid result across a stop and `--resume`.
- Run three repetitions on three pods against one index that no replicate pod writes.
- Make Ragas, the claim-kind classifier and the refusal figures part of the main harness.
- Run every experiment stage in one environment: the standard RTX 4090 pod (D19).
- Measure the shipped app: fix the rate-limit result (D25) and the full-text write on search (D26) in OMRS, before the freeze, not with a harness workaround.

**Non-Goals:**

- Several GPUs or several routers on one pod. The router port and the CUDA device are not settings.
- Any change to models, checkers, prompts, metrics or the statistics plan beyond what the 2026-11-12 redesign set (Exp 35 design D0).
- Any change under `src/omrs/` or `web/` other than the two app fixes D25 and D26 and the llama.cpp reranker backend D27 (operator decisions, 2026-11-12).
- The Exp 35 summary script (Exp 35 task 4.2). This change gives it the join gate, the rebuild report and the refusal figures.
- Parallel local judges.

## Decisions

### D1. One shared gate for hosted calls, in `experiments/_lib/hosted_calls.py`

A gate has one role name, one concurrency limit (an `asyncio.Semaphore`), a classifier and a retry policy. The harness wraps each hosted call seam in a gate: the answer call, the `chat` judge's `judge()` and the Ragas recording seam's `send`. The gate holds the in-flight limit at call level, so a Ragas metric that sends several calls still counts each call.

The library retries and the short OMRS 402 retry (D25) stay as they are. The gate is the outer layer, for the harness's own calls only. It adds the long waits, the attempt limit and the clean stop.

Alternatives considered:

- Raise the library retry count. Rejected: it does not cover a long 402 wait, and it cannot stop a stage cleanly.
- Inject an HTTP transport into the clients. Rejected: OMRS core builds the clients, so this needs a core change.

### D2. Rate-limit classification, backoff and stop

A call is rate-limited when:

- it raises an exception whose status code is 429 or 402 (the `openai` exception carries `status_code` and `response.headers`); or
- an answer result carries the OMRS `rate_limited` record (D25).

The harness never reads the error text. Z.AI's HTTP 429 with code 1302 arrives as a 429 and needs no special case.

Out of credit (operator decision, 2026-11-12): an HTTP 402 with no `Retry-After`, or an answer record with `kind` `out_of_credit`, is not retried. The gate raises `RateLimitStop` at once with a message to top up the provider account.

Wait time:

1. Use `Retry-After` (or `retry-after-ms`) when the exception carries it, or the record's `retry_after_seconds` when it is not null.
2. If that time is above 600 s, stop at once. A long wait in the process is worse than a later `--resume`.
3. Otherwise use an exponential backoff: base 5 s, factor 2, cap 120 s, with equal jitter (half fixed, half random).

The attempt limit is 6 per item by default (`--rate-limit-attempts`). When it is used up, the gate raises `RateLimitStop`. The stage stops taking items, waits for the calls in flight, keeps their results (D3), writes no done-marker and exits with the new code 5 (`EXIT_RATE_LIMIT`, beside `run_arms.py:57`). Under `--arm all`, a child's code 5 stops the later arms (`run_arms.py:136-139`).

Any other error keeps today's path: an error row for answers and local judges, and `JudgeUnavailable` (code 4) for `chat`.

### D3. Ordered commit with a pending file, in `experiments/_lib/ordered_rows.py`

Workers put each finished result in `<stage>.pending.jsonl` at once, flushed and synced. A result holds the question ID, the row and its trace fields. A committer appends rows to `<stage>.jsonl`, and trace rows to `traces.jsonl`, only in frozen question order: the longest finished prefix goes first.

On `--resume`, the stage first commits pending results in order, then sends calls only for items with no row and no pending result. The done-marker is written after the last commit, and the pending file is then removed. The existing `RowFile` key check and partial-line repair (`outputs35.py:95-161`) stay.

Alternatives considered:

- Append in finishing order, then sort at the end. Rejected: `traces.jsonl` mixes stages, so a stage's rows cannot be sorted in place, and the file is out of order while a run is open.
- Keep finished results in memory only. Rejected: a stop would repeat their paid calls.

The byte-identity test injects a fixed clock into the stage context, because rows hold `seconds`.

### D4. Answers: serial retrieval, parallel generation

For each question, the answer stage calls `engine.search(text, **call)` with the search stage's arguments (`run_arms.py:327`), one question at a time. It then calls `engine.answer(text, rows=rows, **call)` through the answer gate. Retrieval and its local query embedding never run in parallel. The evidence therefore does not depend on the concurrency.

Alternative considered: run `engine.answer` in parallel and let it retrieve. Rejected: parallel query embeddings on the llama.cpp server can share a batch, and that can change the vectors at bit level. Keeping retrieval serial removes the doubt at no cost, because retrieval is local and fast.

The pre-freeze test pod session (task 9.2, D24) checks that the evidence chunk IDs match the search stage's IDs on its questions.

### D5. Judges: parallel across answers, serial inside an answer

Redesign note (2026-11-12): Granite Guardian is dropped, so the local judge below is `clef_flash` only.

The judge stage runs several answers at once. Inside one answer, `verify_claims` keeps its one-claim-at-a-time loop (`verify.py:367-371`, unchanged). The `chat` judge is wrapped in the hosted gate. `clef_flash` and `granite_guardian` run with one worker: the router serves one model with `--parallel 1` (`protocol.md` section 7).

A non-rate-limit `chat` failure still raises `JudgeUnavailable` (`stages35.py:356-365`). The difference is that the calls in flight finish first and go to the pending file.

### D6. Ragas stage, in a new `ragas35.py`

`--stage ragas --dataset D --arm A --run N` reads `run<N>/answer.jsonl` and writes `run<N>/ragas.jsonl` with `.done-ragas.json`. It imports the pre-freeze code without change: `require_ragas`, `ragas_llm`, `ragas_metrics`, `judge_answer` and `omrs_chat_seam` from `prefreeze/ragas_stage.py`, and the judge settings from `prefreeze/measure_lib.py`. The judge is built the same way as `prefreeze/measure_live.py:157-192`.

New options:

- `--ragas-host`: the one pinned OpenRouter host, required.
- `--ragas-venv`: the separate Ragas environment.

Each worker has its own `RecordingSeam` and metric set, because the seam's `metric` and `calls` are shared state (`ragas_stage.py:85-87`). Each seam's `send` goes through the Ragas gate.

`judge_answer` swallows metric exceptions (`ragas_stage.py:336-337`), so the stage checks each row before it saves it. A metric error named `RateLimitStop` discards the row and stops the stage. Other metric errors are saved as today.

The question text and the reference answer come from `datasets35.load_questions` (`datasets35.py:76-91`). The contexts are the evidence texts saved in `answer.jsonl` (`stages35.py:227-230`).

The Ragas stage needs the answer stage of its own run only. It does not read the index. Each replicate pod runs it on its own `run<n>/` right after its answer and judge stages (D19). The `answer_relevancy` embeddings come from the pod's local router with the pinned Qwen3-Embedding-4B Q8_0 GGUF, checked with `verify_llamacpp_runtime` (`experiments/_lib/llamacpp_runtime.py:181`) before the first paid call. The router holds one model at a time (`arms.py:45`), so Ragas runs after the local judges and the router loads the 4B model again.

### D7. Pod-local state and settings, per-pod run records

A new option `--local-dir PATH` moves `config/` and `state/` out of `<out>` (`outputs35.py:61-73`). Without it, the layout is unchanged.

On replicate pods:

- The procedure sets `--local-dir` to a folder on the container disk. This meets gotcha 17 and stops three pods from rewriting one `omrs.jsonc`.
- Each pod has its own git checkout on the container disk, so `guard_run` writes that pod's own `output/run-records.jsonl` (`live35.py:59`).
- The network volume holds only `<out>` (store, index markers, fingerprint and run folders), the data and the GGUF files.

To record the concurrency values that a default supplied, `run_arms.py` passes `guard_run` an explicit command. The command is the `argv` with every resolved concurrency and attempt value added.

### D8. Seal step and index fingerprint

A new stage `seal` runs on the build pod after every index of a dataset is built. It checks the index markers of the dataset's 9 indexes (one per embedder and chunk size; four under the arm design before 2026-11-12). It then writes `<out>/<dataset>/index-fingerprint.json`: for each collection, the table version, the dataset epoch, the resolved sparse backend of each hybrid arm, and the full-text index row counts (or none). It also writes the build environment record `<out>/environment.json` (D19).

The seal creates and refreshes no full-text index. After D26, OMRS builds the index at the end of an ingest when the resolved backend is `native`, and a native query never writes. Where a hybrid arm resolves `native`, the seal refuses when that index is missing or has unindexed rows. With the protocol's BM25 hybrid arm (Context), the fingerprint records `bm25` and no full-text state.

Every hybrid-on setup pins its backend (operator decision, 2026-11-12; written for the hybrid arm, which the redesign replaced). `arms.settings_values` (`arms.py:149`) writes `retrieval.hybrid_sparse_backend: bm25` into the scratch `omrs.jsonc` of every hybrid-arm process. The existing `router_env.check_resolved` (`experiments/_lib/router_env.py:295`) then refuses when an environment variable or `.env` entry overrides it, because those sources outrank the file. `_resolved` (`run_arms.py:182`) adds the value to the trace settings. So a changed default cannot switch the arm to native full-text.

Why the fingerprint stays: it is a safety check, not a race guard. It proves that no replicate stage wrote the shared store, whatever the cause: a later OMRS change, a wrong option, or a stage run against the wrong folder.

Each search, answer and judge stage:

- reads the fingerprint before its first query and refuses on a difference, including a hybrid-on setup that resolves another sparse backend;
- reads it again after its last item;
- records both checks in its done-marker.

The checks open tables read-only through the existing readers (`src/omrs/core/vectordb/lancedb/meta.py:89-124`).

Alternative considered: mount the volume read-only on replicate pods. Rejected: RunPod network volumes mount read-write, and the check is still needed to prove it.

### D9. Index folder apart from the output folder

A new option `--index-from PATH` gives `Layout` a separate index root for `lancedb`, the index markers and the fingerprint. The build pod uses it for its FreshStack recheck on the real indexes (`--qids 77536364,77762811 --index-from <shared out> --out-dir <recheck folder>`). The recheck therefore reads the real indexes and writes nothing to the shared folder.

### D10. Join step, in a new `join35.py`

`join35.py --out-dir <out> --records <pod1.jsonl> <pod2.jsonl> <pod3.jsonl>` checks, for each dataset, arm and run 1 to 3:

- the done-markers of `search`, `answer` and `judge-{clef_flash,chat}` (Granite Guardian dropped on 2026-11-12);
- equal `*.key.json` contents across runs;
- clean fingerprint checks in each done-marker;
- a passing `rebuild.json` for each dataset (D20);
- at least one run-record line whose command names that run.

It also checks the `ragas` and `claimkinds` done-markers, that each run's `ragas.jsonl` has one row per answer, and that each run's environment record equals the build record (D19). It merges the pod run records into the Mac checkout's `output/run-records.jsonl`. It appends only lines the file does not hold, in start-time order, and never rewrites a line. It writes `<out>/join.json` with `ok` and every failure.

`determinism_stage` (`stages35.py:416-453`) refuses without `join.json` `ok`, and adds the machines of each run to `determinism.json`. The join reads only saved JSON files, so it runs on the Mac after the shared folder is copied back without `lancedb/` (D19 allows this).

### D11. Machine and environment record

Each stage that runs a model, sends a model call or reads the index appends one line to `run<n>/machine.jsonl` at its start. The line holds the host name, `RUNPOD_POD_ID` when set, and the environment record (D19). A resumed stage on a new pod adds a second line, and the report shows both.

### D12. Named questions

`--qids a,b` selects those questions in frozen order and makes the run a smoke run (`run_arms.py:84-85`). An unknown ID raises `DatasetError` before any call.

### D13. Claim kinds: what counts where (pre-freeze amendment, 2026-11-12)

**Revision (redesign, 2026-11-12).** H-CC and Granite Guardian are dropped. The claim-kind rule stays on its own: primary faithfulness per answer setup and checker (GLM-5.3, Clef-Flash) uses factual and mixed claims, and refusals are reported apart. The table below no longer has an H-CC row. The paragraphs after it explain why the rule was first written for H-CC; they stay as history. The "per-checker bounds" row now bounds faithfulness per answer setup, not an H-CC gap. "Per arm" reads "per answer setup".

Each claim gets one kind: factual claim, refusal or mixed. Mixed (a checkable fact plus a scope limit) counts as a factual claim. A negative finding that answers the question ("no debt securities are listed") is a factual claim. Only a refusal (the sentence states only that the sources do not cover something) leaves the primary figures.

| Figure | Claims | Status |
| --- | --- | --- |
| Faithfulness per arm (each checker) | factual and mixed | primary |
| Refusal rate per arm and dataset | refusal | primary descriptive |
| Each checker's unsupported rate and kappa against GLM-5.3 | refusal | descriptive |
| Faithfulness | all claims (the 2026-11-11 definition) | secondary robustness |
| Per-checker bounds: one checker's refusal verdicts all supported, then all unsupported, others fixed | all claims | secondary robustness |

Reason: faithfulness and H-CC are meant to measure whether checked facts are backed by the sources. A refusal is a statement about retrieval, not a fact from a source. The checkers also grade refusals very differently: Granite Guardian says unsupported on 67% to 94% of smoke refusals, with a kappa of about 0 against GLM-5.3. With refusals in, H-CC would partly measure refusal grading.

The smoke data (5 questions per dataset, direction only) suggest that the FreshStack gap moves from +19.3 points (all claims) to +16.3 points (factual claims only). That is close to the 15-point line. The rule is chosen for what H-CC means, not for this outcome. The protocol amendment says this openly, and the all-claims figure stays in the report.

H-CC was registered on 2026-11-11, before the freeze. The change of its claim population is a dated pre-freeze amendment in `protocol.md` section 4.4 and an ADR-119 amendment note. The other H-CC rules stay. A question with no factual claim in any arm or run leaves that dataset's bootstrap, as a question with no claims did before.

Mechanics, in a new `refusals35.py`:

- The claims are split again from the saved answer text with `split_claims` (`src/omrs/core/answer/verify.py:177`), the splitter the judges used. They are matched to the verdicts by index (the judge row holds no claim text, `stages35.py:346-354`). If the counts differ, the step stops with the location named.
- A `claimkinds` stage runs on each replicate pod after its judge stages. It writes `run<n>/claim-kinds.jsonl`, keyed by the SHA-256 of the question ID and the claim text, and `.done-claimkinds.json`. `--resume` skips saved kinds. A per-run file avoids three pods writing one file on the network volume. The report counts a claim text that got different kinds in different runs.
- The report step `refusals35.py report --out-dir <out>` reads saved files only and runs on the Mac. It refuses without a passing join. It writes `refusals.json` with every figure in the table above.
- Wilson intervals and paired bootstrap come from `experiments/_lib/stats_d6.py:43` and `:140`.

### D14. Classifier: fixed-prompt LLM (operator decision, 2026-11-12)

| | Written rule (patterns) | Fixed-prompt LLM classifier |
| --- | --- | --- |
| Mixed sentences | Weak. A pattern sees "not covered" but cannot tell whether a checkable fact sits beside it. | Strong. It reads the whole sentence and the question. |
| Paraphrase | Weak. The pre-freeze regular expression flagged about 9 of 15 sentences wrongly and missed some refusals. | Strong. |
| Reproducibility | Exact. | Good with a pinned model and host, temperature 0, a fixed seed and a fixed prompt. The saved kinds are the record; they are never recomputed. |
| Cost and time | None. | One short hosted call per claim, in a `claimkinds` stage on the replicate pod. |
| Independence from H-CC | Full. | Full when the model is outside the checker families. |

Decision: the fixed-prompt LLM classifier, with `openai/gpt-oss-120b` on OpenRouter, pinned. It is the Ragas judge already pinned in the protocol: reasoning `low`, temperature 0, fixed seed, one pinned host. It is not GLM-5.3, Granite Guardian or Clef-Flash, so it cannot favour one side of H-CC. It is not the answer model's family either.

The prompt gives the three kinds with short examples. The examples come from smoke claims outside the gate sample. The model sees the question and the claim sentence only, never the evidence and never a verdict. The classifier version is the SHA-256 of the prompt, the model id, the host, the reasoning level, the temperature and the seed. Calls go through the hosted gate (D1) with their own concurrency setting.

The pre-freeze regular expression is scored on the same gate sample as a baseline only.

Rejected alternative: the written rule. It is exact, but it cannot tell a mixed sentence from a refusal, and the pre-freeze regular expression shows the cost.

### D15. Classifier gate before the freeze (thresholds approved, 2026-11-12)

1. The protocol states the pass thresholds before labelling starts:
   - agreement on refusal against not refusal of at least 0.90;
   - refusal recall of at least 0.90.

   Precision is reported, not gated.
2. `refusals35.py sample --seed 20261112 --n 100` draws the gate sample from the valid smoke claims only (BioASQ, FinanceBench, the FreshStack rerun; not the invalid first FreshStack smoke). It draws about a third from each dataset. Inside each dataset, half come from claims the pre-freeze regular expression flags and half from the rest, so the sample holds enough refusals. The regular expression is independent of the new classifier, so this split does not favour it.
3. The prompt examples and any rule tuning use only smoke claims outside the sample.
4. The classifier calls for the gate sample run as a stage on the 4090 pod (the build pod). `refusals35.py page` writes one static HTML labelling page into the restricted output folder. The page shows the question and the claim, and asks for one of factual claim, refusal, mixed or "can't tell". It shows no kind and no verdict. It keeps the labels in the browser and saves them as a JSON download. It loads nothing from the network.
5. `refusals35.py gate` scores the saved kinds and the baseline against the labels. It reads saved files only, so it runs on the Mac. It gives stratum-weighted agreement and refusal recall, with the unweighted values and the "can't tell" count beside them. It writes `gate.json` with pass or fail.
6. The classifier is frozen only on a pass. A fail blocks the freeze of the classifier, and the operator decides the next step.

### D16. Ragas and refusals: check the source, do not assume

The Ragas stage scores every answer with no special handling (D6). The frozen metric set has no answer-correctness metric (`prefreeze/measure_lib.py:38`). The expected penalty for a wrong refusal is in `answer_relevancy`, which is said to score a non-committal answer 0. Task 7.5, an early implementation task, reads the `AnswerRelevancy` source of Ragas 0.4.3 in the pinned Ragas environment, and checks it with Context7. If the source confirms it, `protocol.md` states it with the file and line. If not, `protocol.md` and the report list it as an open item, and nothing claims the penalty. The report states the result either way.

### D17. File size plan

- Move `answer_stage` and `judge_stage` out of `stages35.py` into `answers35.py` first, as a pure move with the existing tests green.
- New work goes into new modules: `answers35.py`, `ragas35.py`, `join35.py`, `refusals35.py` (split into `refusals35.py` and `claimkinds35.py` if it nears 500 lines), `rebuild35.py`, `experiments/_lib/hosted_calls.py` and `experiments/_lib/ordered_rows.py`.
- New tests go into new files under `tests/`.
- If `run_arms.py` nears 500 lines, its argument parser moves to `cli35.py`.

### D18. Starting concurrency values

The starting values are: answers 16, `chat` judge 4, Ragas 16, `claimkinds` 16, rate-limit attempts 6. The pre-freeze test pod session (D24) measures them and sets the values the protocol freezes. The basis for the start values:

- OpenRouter paid models have no platform rate cap, but a spend budget can return 402 with `Retry-After`.
- DeepInfra allows 200 concurrent requests per model.
- Z.AI publishes no concurrency number and returns 429 with code 1302 when a caller goes over.

### D19. One environment for every stage (operator decision, 2026-11-12)

**Revision (GPU choice, 2026-11-12).** "The standard RTX 4090 pod" below now reads "the pod of the GPU type chosen by the D24 rule". The rule is otherwise unchanged: one image, one llama.cpp build (b11941), one set of GGUF files (now with the three reranker files) and one GPU type for every stage, including the parallel index build pods (D32). "The three judges" reads "the two judges".

Rule: every experiment stage runs on the standard RTX 4090 pod: same image, same llama.cpp build (b11941), same GGUF files. That covers ingest, seal, rebuild, search, answer, the three judges, `ragas`, `claimkinds`, the classifier calls for the gate and the live calibration. A stage that sends only hosted calls still runs on the pod. Only steps that read saved files and write checks, statistics or reports run on the Mac: `join35.py`, determinism, `refusals35.py gate` and `report`, the labelling page and the Exp 35 summary. The protocol states this rule (task 10.1).

The environment record:

- the GPU model from `nvidia-smi`;
- the container image, from `EXP35_POD_IMAGE`. The image is `runpod/base:1.6.0-cuda1281-ubuntu2404`, pinned by digest (`runpod/base@sha256:<digest>`) at the freeze (operator decision, 2026-11-12). The Mac pod-creation script passes that one pinned value as the pod image and as `EXP35_POD_IMAGE`, so the two cannot differ. A value without `@sha256:` refuses the stage;
- the llama.cpp build and the SHA-256 of each plan GGUF, from `verify_llamacpp_runtime`.

The `seal` stage writes the build record to `<out>/environment.json`. Each stage that runs a model, sends a model call or reads the index compares its own record with it at start, and refuses on any difference or a missing field. The join fails a run whose recorded environment differs. A Mac has no `nvidia-smi` and no `EXP35_POD_IMAGE`, so a model stage refuses to start there.

Ragas runs on each replicate pod on its own run, right after the answer and judge stages (D6). The three pods use the same pod spec, so the three runs are scored in the same environment. Each worker keeps its own call records, and `--resume` skips saved rows.

### D20. Rebuild comparison (G2, Exp 35 task 4.2 brought into this change)

**Revision (redesign, 2026-11-12).** The rebuilt index is `e4b-c1024` (Qwen3-Embedding-4B at 1,024 tokens), the middle cell of the factorial, and the comparison search runs the setup `e4b-c1024-roff-hoff` (no reranker, no hybrid, so the check isolates index building). Everything else below holds, with "setup" for "arm".

On the build pod, after the 9 index builds per dataset and the seal:

1. A fresh process builds the `e4b-c1024` index again into a separate store: `run_arms.py --setup e4b-c1024-roff-hoff --stage ingest --out-dir <rebuild folder>` (was `--arm documents-profile-4b`).
2. `--stage search --run 1` runs on the rebuilt index into the rebuild folder, and on the shared index into a build-pod check folder (`--index-from <shared out>`).
3. `rebuild35.py --a <check search.jsonl> --b <rebuild search.jsonl>` compares the ranked IDs per question with `compare_runs` (`experiments/_lib/determinism.py:90`). That helper covers the union of questions, so a question on one side only is a mismatch. It writes `<out>/<dataset>/rebuild.json` and exits with code 3 on a mismatch.

G1 compares the replicate runs with each other, so the build-pod search of the shared index stands for run 1. The join requires a rebuild report for each dataset. Stop rule (operator decision, 2026-11-12; fixed in `protocol.md` section 6): if a rebuild check fails, the replicate pods do not start. The cause is found and fixed, the indexes are built again, and `seal` and the rebuild check run again. There is no choice on the day. The harness enforces it: a search, answer or judge stage that writes into the shared output folder refuses to start without a passing `rebuild.json` for its dataset. The build pod's own check searches use `--index-from` and a separate folder, so the rule does not block them. A failed check stays in the record and the report.

### D21. Cohen's kappa (operator approval, 2026-11-12)

One function `cohen_kappa(a, b)` goes into `experiments/_lib/stats_d6.py`, test-first. Its known-answer test is a 2 x 2 table with 20, 5, 10 and 15 items: observed agreement 0.70, chance agreement 0.50, kappa 0.40. It raises `ValueError` on empty or unequal inputs. It returns NaN when chance agreement is 1 (every label the same), and the report prints "not defined". The refusal report and the Exp 35 summary use it.

### D22. Replicate pod time, Ragas included

**Revision (redesign, 2026-11-12).** The figures below the revision assumed six arms and 19,440 answers. The redesign has 12 answer setups x 3 runs x 1,160 questions = 41,760 answers, 13,920 per replicate pod. Claims per answer stay at about 4.47 (smoke data), so about 186,700 claims in all and 62,200 per pod. Only GLM-5.3 and Clef-Flash judge. Times are for an RTX 4090; the GPU choice (D24 revision) may change the GPU-bound rows.

| Stage (per replicate pod) | Basis | Hours |
| --- | --- | ---: |
| Answer-stage retrieval (12 setups, 6 with the reranker) | Rerank tokens as in D23, at the chosen reranker size: 0.6B 5.5 h, 4B 10.8 h, 8B 15.5 h | about 11 (4B assumed) |
| answer | 26.6 s per answer serial, concurrency 16 | 6.4 |
| `clef_flash` | 7.5 rows/s, times 1.5 for the longer evidence at 2,048 tokens | 3.5 |
| `chat` (GLM-5.3) | 3.45 s per claim per worker (operator figure); concurrency 8 per pod | 7.5 (15 at concurrency 4) |
| `ragas` (five metrics) | 117 s per answer serial for the four pre-freeze metrics, plus about 23 s for `AnswerCorrectness` (about 3 short calls without the contexts; estimate, measured in the test pod), concurrency 16 | 33.8 |
| `claimkinds` | about 2 s per call, concurrency 16 | 2.2 |
| **Sum** | one stage at a time | **about 65** |

GLM-5.3 needs about 179 worker-hours in all (186,700 claims x 3.45 s). Three pods at concurrency 8 each (24 at once on one Z.AI Coding Plan key) finish the `chat` stage in about 7.5 h. The test pod session measures whether Z.AI accepts 24 at once without 429 code 1302; at concurrency 4 the stage takes about 15 h per pod. There is no per-token cost.

Older text (six arms, 19,440 answers, three checkers):

Per replicate pod: 19,440 / 3 = 6,480 answers. Claims per answer from the valid smoke data: 804 claims over 180 answers, about 4.5 (BioASQ 278, FinanceBench 143, FreshStack rerun 383; 60 answers each). That gives about 29,000 claims per pod. This assumes the same claims per answer across the main question mix.

| Stage | Basis | Hours per pod |
| --- | --- | ---: |
| answer | 26.6 s per answer serial (pre-freeze `answers20.jsonl`), concurrency 16 | 3.0 |
| `clef_flash` | 7.5 rows/s (protocol section 4.4) | 1.1 |
| `granite_guardian` | 2.3 rows/s (protocol section 4.4) | 3.5 |
| `chat` (GLM-5.3) | 2.8 rows/s from the pre-freeze runner (default concurrency 8, `prefreeze/run_glm_chat.py:199`), halved for concurrency 4 | 5.8 |
| `ragas` | 117 s of call time per answer serial, 13 calls (pre-freeze `ragas20.jsonl`), concurrency 16 | 13.2 |
| `claimkinds` | about 2 s per call (assumed), concurrency 16 | 1.0 |

The sum, with every stage in a row, is about 28 h per pod (27.6 h), search not included. Without Ragas, it is about 14 h. Ragas is now the largest stage, about half of the pod time. The `chat` stage uses no router, so a second process beside the local judges could save about 4.6 h. This change does not do that: two processes would append to one `traces.jsonl`, and the ordered-row rule (D3) holds only inside one process.

These are estimates. The local judge rates come from LLM-AggreFact rows, which have longer documents than our claims. The pre-freeze test pod session (D24) measures Ragas seconds per answer and the other rates, and replaces this table before the freeze.

### D23. Budget: estimate and ceiling (revised 2026-11-12; was one total cap of $250)

**Revision (redesign, 2026-11-12).** The $250 cap is gone. The operator has about £2,000 to £3,000. Estimate, on an RTX 4090 at $0.89 per hour (re-checked live before each pod):

| Item | Basis | Pod hours | Cost |
| --- | --- | ---: | ---: |
| Index builds, 9 per dataset, 4 datasets | Per build of all corpora at one chunk size: 0.6B 2.9 h, 4B 3.4 h, 8B 3.7 h (protocol 4.5), plus about 0.25 h for Legal; 3 chunk sizes. Plus about 0.5 h start-up per parallel pod (D32) | 32 + 4.5 | $33 |
| Search stage, 72 setups | 100 candidates per query; candidate tokens about 460 / 920 / 1,840 on long documents and about 400 to 420 on short ones, plus 100 prompt tokens; 247 million tokens per reranker size and hybrid level over the three chunk sizes and three embedders. Reranker speed assumed equal to the measured embedding speed of the same size (0.6B 24,700, 4B 12,700, 8B 8,800 tokens/s). Non-reranked setups under 1 h | 97 | $86 |
| Rebuild check and FreshStack recheck | One `e4b-c1024` rebuild per dataset set, plus a small search | 5 | $4 |
| Replicate pods | 3 x about 65 h (D22) | 195 | $174 |
| Pre-freeze test pod session and GPU timing | About 6 h on the 4090 plus about 10 min on each other GPU (D24) | 7 | $8 |
| Network volume | About 100 GB for about 2 months | | $14 |
| Answers | 41,760 x $0.0029 (measured at about 1,024-token chunks), scaled by evidence size (x0.87 at 512, x1.27 at 2,048 on average) | | $127 |
| Ragas (five metrics) | 41,760 x $0.0019 for the four pre-freeze metrics plus about $0.0004 for `AnswerCorrectness` (three short calls without the contexts), same scaling | | $100 |
| Claim classifier | About 186,700 short calls on `openai/gpt-oss-120b` | | $9 |
| GLM-5.3 claim checks | Z.AI Coding Plan, no per-token cost | | $0 |
| **Total** | | **about 341** | **about $555** (A1b total; A2 total in D35) |

Rounded estimate after A1b: **$555, ceiling $830** (history). Final estimate after A2, the oracle run and A2c: **$650, ceiling $975 (1.5 x)**; see D35 and D37.

The largest unknown is reranker speed. llama.cpp issue #30422 reports rerank mode about 6 times slower than it should be. At 3 times slower than assumed, the search stage and the answer-stage retrieval add about 257 pod hours (about $229), and the total is about $870, still under the ceiling. At 6 times slower, the total passes the ceiling, and the stop rule triggers before the freeze. The test pod session measures the real speed.

Stop rule, checked three times:

1. **Before the freeze**, in the test pod session (D24): the same sum with the measured build hours per chunk size, reranker throughput per size, answer and Ragas seconds and hosted cost per answer. Above $975, the operator decides before the freeze.
2. **On the build pods, after the search stage**: real pod cost so far plus the projected replicate cost. Above $975, the replicate pods do not start and the operator decides.
3. **While the replicate pods run**: RunPod billing plus OpenRouter spend, read at each stage end. At $975 the next stage does not start. The OpenRouter key carries a credit limit equal to the hosted share of the ceiling (about $450), so an overrun ends as a clean `out_of_credit` stop (exit code 5, D2).

Older text (the $250 cap):

The whole run has one cap: $250, for pods and hosted calls together. There are no per-pod hour caps. Task 10.2 writes the cap into `protocol.md` as Exp 35 task 1.11.

The cap is checked twice:

1. **Before the freeze**, in the test pod session (D24). The extrapolated total is: the measured index-build hours (protocol section 4.5 until the build pod replaces them) times the pod price, plus three replicate pods at the measured D22 hours times the pod price, plus the measured hosted cost per answer (reported `cost_usd` of answer, judge, Ragas and classifier calls) times 19,440. Above $250, the operator decides before the freeze.
2. **After the indexes, on the build pod** (a light re-check, no calibration). The same sum, with the real build pod cost so far in place of the index estimate. Above $250, the procedure stops before the replicate pods start and asks the operator.

### D24. Pre-freeze test pod session (operator approval, 2026-11-12)

**Revision (redesign, 2026-11-12).** The session grows to about 6 h on the 4090 and adds a short GPU-choice step. It now also measures:

1. **Reranker files.** For each Qwen3-Reranker GGUF (0.6B from `ggml-org`, 4B and 8B from the candidate community repositories): load with `pooling: rank`, send one relevant and one irrelevant pair (expect a score near 1 and near 0), and compare the ranking of 20 query-passage sets with the model card's transformers recipe. A file that fails is not pinned (Exp 35 open question A1-5).
2. **Reranker throughput** at each size, in pairs per second and tokens per second, at 512-, 1,024- and 2,048-token passages, with the 100-candidate pool.
3. **VRAM:** the 8B embedder and the 8B reranker loaded together on the router (`llamacpp_router_models_max` 2), peak VRAM, and whether the router swaps a model out between the query embedding and the rerank.
4. **Index build time per chunk size** on a fixed slice of each corpus, for each embedder size.

**GPU choice (operator instruction, 2026-11-12).** Candidates: RTX 4090 (24 GB), L40S (48 GB), H100 (80 GB). Before each pod: re-check the live price and stock, quote them, and wait for the operator's go. On each GPU, run the same fixed job of about 10 minutes:

- embed a fixed sample of 2,000 chunks (FinanceBench and FreshStack, at 1,024 and 2,048 Qwen3 tokens) with Qwen3-Embedding-8B Q8_0;
- rerank a fixed set of query-passage pairs with Qwen3-Reranker-8B Q8_0;
- record chunks per second, pairs per second, peak VRAM, whether the 8B embedder and the 8B reranker load together without swapping, the llama.cpp build, the driver version and the image digest.

Decision rule, written into `protocol.md` before the first measurement: among the GPUs that hold the 8B embedder and the 8B reranker together without swapping, choose the one with the lowest projected total GPU cost for the main build and search work (9 index builds per dataset plus 72 search setups), using the measured rates and the live hourly price. When two GPUs are within 10% on that cost, choose the faster one. The protocol records the measurements, the prices with their date and the choice.

Rule: every main-run pod (the index build pods, the search pods and the three replicate pods) uses that one GPU type, and every stage runs on it. GPU types are never mixed. The environment record (D19) holds the GPU model, so a stage on another GPU type refuses to start. The earlier 4090 pre-freeze runs (smoke runs, LLM-AggreFact runs, timing) were preparation, not results.

If the chosen GPU is not the 4090, the D22 and D23 rows for GPU-bound stages are scaled by the measured rates and the live price before the freeze.

Older text (2 h session on the 4090 only):

One short session, about 2 h and about $2, on the standard RTX 4090 pod with the pinned image (D19). It runs before the freeze (G7), after this change's code is merged and its tests pass. The operator gets the price quote and gives the go before the pod is created. The pod is deleted when the session ends.

The session uses its own smoke folder and its own small indexes (`--limit` and `--corpus-sample`, which ingests the gold documents of the chosen questions plus seeded others). It never touches the main output folder and writes no main run record. It does three things:

1. **Calibration.** It runs answers, the `chat` judge, Ragas and `claimkinds` at the D18 starting values on the smoke answers. It records per role the 429 and 402 counts, waits, stops and calls per minute. It halves a value that hit a rate-limit stop and repeats that role once. It measures wall seconds per answer per stage and the reported cost per answer. It runs the first $250 cap check (D23). The frozen protocol holds these measured values, not provisional ones.
2. **FreshStack recheck.** It answers and judges FreshStack questions `77536364` and `77762811` in every arm (`--qids`). The pass rule: every `answer-summary.json` has `failed` 0 and every judge summary has `errors` 0. The build pod repeats this recheck on the real indexes before the replicate pods.
3. **End-to-end run of every new stage once:** ingest, `seal`, search, parallel answers, the three judges, `ragas` and `claimkinds`, all as run 1, then a smoke join on the one-run toy (`join35.py --smoke --runs 1`). The rebuild check runs once on a toy rebuild of one small index.

The session's figures go into `protocol.md` as a dated calibration note before the freeze. A failure in step 2 or 3 is fixed in code and the session runs again before the freeze.

### D25. App fix A: a rate-limited answer is a typed error (operator decision, 2026-11-12)

What happens today:

- A provider error leaves `run_synthesis` and becomes `Generation failed: <type>: <detail>` in `error` (`src/omrs/core/answer/stages.py:171-185`). The result has status `error`, `answer` null and `failure_stage` `generation` (`results.py:134-166`), on both the standard path (`core/answer/pipeline.py:302-310`) and the user-profile path (`core/answer/graph_adapters.py:274-283`). No field marks a rate limit.
- HTTP 429 is already retried below OMRS: `llama-index-llms-openai` retries `RateLimitError` 3 times, honours `Retry-After` up to 120 s and stops after 60 s (`llama_index/llms/openai/utils.py:272-350`); the `openai` client retries 429 itself (`openai/_base_client.py:853`). OMRS builds the client with the default `max_retries=3` (no override in `src/omrs/`). HTTP 402 is retried by neither.
- The web chat does not save an error result as a turn (`web/src/chat/useChatSession.ts:157`). It shows "The model could not write an answer from the evidence." (`web/src/chat/answerStatus.ts`, `failureLine`). That line blames the evidence or the model, so the user cannot tell that waiting would help. MCP `answer_documents` returns the result unchanged (`transports/mcp/answer.py:262-277`).
- Evidence that it happens: the serial pre-freeze answer run met upstream 429s on the DeepSeek answer model ("temporarily rate-limited upstream"); the library retries recovered after about 8 s (`DATA/.../prefreeze-final/measure.log`, lines 215-235, 2026-11-10 23:56).

Bug score: likelihood 4 (429s seen in a serial 20-answer run; an unrecovered one needs the library's 60 s to run out, or a 402, which is never retried; the parallel harness and MCP agents raise the rate). Impact 3 (a clear error that the user can retry, but labelled as a model or evidence failure, and untyped, so an automated caller must parse text or count it as a failed answer). Score 12: fix.

Decision:

1. A new core module `src/omrs/core/answer/rate_limits.py` classifies an exception by duck typing: `status_code` 429 or 402, and `retry-after` or `retry-after-ms` from `response.headers`. Core imports no provider library. It gives a record `{kind, http_status, retry_after_seconds}`. `kind` is `rate_limit` for a 429, and for a 402 with `Retry-After` (a spend budget in flight). It is `out_of_credit` for a 402 with no `Retry-After` (operator decision, 2026-11-12).
2. `synthesise_answer` wraps the completion seam inside `_counting_complete`. It retries only an HTTP 402 that carries a `Retry-After` of 30 s or less, at most 2 more attempts, with that wait. It never retries `out_of_credit`. It adds no retry for 429, because two library layers already retry it; a third layer would multiply the attempts.
3. A rate limit that remains gives `SynthesisOutcome.rate_limited` and a fixed message per kind. `rate_limit`: "Generation failed: the answer model's provider is limiting requests (HTTP 429). Wait, then ask again." `out_of_credit`: "Generation failed: the answer model's provider account is out of credit (HTTP 402). Top up the account, then ask again." `stage_failure_result` adds the optional key `rate_limited`. Both call sites pass it, so the two paths agree.
3a. The claim judge gets the same record (operator decision, 2026-11-12). `run_verification_stage` catches every judge exception and returns `verification_skipped` (`core/answer/verify.py:461-463`); the answer keeps its status, as for any judge failure (ADR-059). The catch now classifies the exception: a rate limit gives `VerificationFields.rate_limited` and a fixed reason per kind. `answered_result` (`results.py:180-230`) adds the optional key `verification_rate_limited`, with the same record shape. The 402 retry of item 2 also wraps a judge that is a plain completion seam, in `verify_answer` before `as_judge` (`stages.py:291-293`). A typed local judge gets the classification only. The Exp 35 harness runs its own judge stage through its gate, so it does not use this key.
4. The status stays `error`. A new status value would break the closed status set (`grounded-answer-synthesis`, "Status, failure stage and completion source take closed values"), and the web chat saves every non-error result as a turn (`useChatSession.ts:157`), so a new status would save the rate limit as an answer.
5. `AnswerResponse` in `src/omrs/transports/api/openapi.yaml` declares `rate_limited` and `verification_rate_limited`, with one closed record schema, because the schema is closed (`additionalProperties: false`; `tests/unit/test_answer_response_contract.py`). The HTTP status of the answer route stays 200: failures come back inside the result (`openapi.yaml:717-723`).
6. The web chat shows a line per kind in `failureLine` (wait for `rate_limit`, top up for `out_of_credit`) and keeps Retry. `web/src/api/documents.ts` adds the optional field. MCP and the CLI need no code change: MCP returns the dict and never raises (gotcha 1); the CLI prints `error` and exits 1.

Callers after the fix: web chat (new line), MCP `answer_documents` (new key, no raise), `Engine.answer` (new key), CLI (new message text), the Exp 35 harness (reads the key, D2). The web chat shows `verification_skipped` as today; showing the judge record's kind there is not in this change.

### D26. App fix B: a native full-text query never writes (operator decision, 2026-11-12)

What happens today:

- `query_native_sparse` creates the index when it is absent (`fts.py:180`, `:75-90`) and runs `table.optimize()` when rows are unindexed (`fts.py:182-192`, `:101`). Both commit a new table version on a read path. On the first query of a large collection, the query waits while the index is built.
- A new table version on a read invalidates the BM25 cache of every other process, because the Lance validity token is `(omrs_dataset_epoch, table.version)` (root gotcha 14). It also breaks any read-only check of the store, such as the Exp 35 fingerprint.
- Two processes that query at once can both run `optimize()`. A failed commit raises, and the pipeline falls back to BM25 for that query with a log warning only (`fts.py:170-174`; `hybrid-retrieval`, "Native fallback remains explicit").
- The write is not needed for correct results. The LanceDB FTS query scans unindexed rows and honours delete tombstones at query time, and a raw query does not change the index statistics (`tests/test_lancedb_native_fts_contract.py:253-282`). A query on a table without an index raises `ValueError`, which the pipeline already routes to BM25 (same file, docstring lines 31-33).
- Chroma has no native sparse query: the base method refuses (`core/vectordb/base.py:126`), and `auto` resolves `bm25` there. So Chroma has nothing to fix and gets a no-op.

Bug score: likelihood 2 (needs the opt-in `native` or `auto` backend; the default is `bm25`, the live app sets none, and the Exp 35 hybrid arm is BM25, see Context). Impact 4 (a read path commits writes: a slow first query, BM25 cache churn in other processes, and under concurrency a silent switch of one query to BM25 with only a log warning). Score 8: fix.

Decision:

1. `query_native_sparse` only reads. It calls neither `ensure_fts_index` nor `refresh_fts_index`. With no index, the query raises and the existing fallback warns and serves BM25. The warning names the remedy: run an ingest of the collection.
2. A new store method `prepare_native_sparse(collection)`: a no-op on `VectorStore` (`base.py`), so Chroma inherits it; on `LanceFTSMixin` (`fts.py`) it creates the index when absent and refreshes it when rows are unindexed. It goes in `fts.py`, because `lancedb/store.py` has 488 lines.
3. `ingest_path_async` calls it once at the end of every run when the resolved `retrieval.hybrid_sparse_backend` is `native`, also when the run wrote nothing. So an ingest of an existing collection is the remedy, with no new command. A failure logs a warning and does not fail the ingest. `core/ingestion/pipeline.py` has 458 lines; if the call does not fit, a helper goes in `core/ingestion/writer.py`.
4. Deletes do not refresh. Tombstones keep query results correct, and the next ingest folds them in. A delete-time refresh would run `optimize()` once per replaced file during a re-ingest.
5. The mixed-coverage warning text changes from "The next native query refreshes the index" to name the next ingest (`core/retrieval/sparse_dispatch.py:153-160`). The `fts.py` module docstring changes to match.
6. Gotcha 14 still holds: writes still advance the table version and invalidate BM25 caches. Reads no longer do. Gotcha 17 fits better: the stdio MCP server's search no longer writes the store.

7. The baseline requirement "Existing collections are usable without re-ingestion" says an unindexed row is left out of the sparse ranking. The contract tests show the opposite: the FTS query finds a row written after the index, and drops a deleted row (`tests/test_lancedb_native_fts_contract.py:253-282`). The MODIFIED text matches the tests; the sparse-vector rule is unchanged. Spec only: no code follows the old wording.

Spec: `hybrid-retrieval` gets three MODIFIED requirements ("Native FTS lifecycle is specified and durable", "Native queries never serve a stale FTS index", "Existing collections are usable without re-ingestion") and one ADDED requirement ("A native sparse query never writes to the store").

### D27. App addition C: a llama.cpp reranker backend (redesign, 2026-11-12)

What the experiment needs: Qwen3-Reranker at 0.6B, 4B and 8B on the same pinned llama.cpp runtime as the embedders (ADR-103), inside the shipped OMRS search path, so the benchmark measures the app.

Fact check (2026-11-12):

- llama.cpp supports Qwen3-Reranker through `--reranking` (embeddings with pooling `rank`) and `/v1/rerank`. Support came in ggml-org/llama.cpp PR #15824 (merged 25 September 2025, release b6578), so b11941 has it. The GGUF must come from llama.cpp's own `convert_hf_to_gguf.py` after that PR; other conversions lack the classifier head and fail to load or give near-zero scores (issues #13820, #16407).
- llama-server builds the Qwen3 prompt itself from a `rerank` chat template stored in the GGUF, with the model card's default instruction ("Given a web search query, retrieve relevant passages that answer the query"). The model card notes that a task-specific instruction can add about 1% to 5%; a custom instruction needs a GGUF metadata edit, so every setup uses the default.
- Open issue #30422: rerank mode runs about 6 times slower than expected on a b11456 build (scores correct). The test pod measures our speed (D24).
- Files: Qwen publishes no GGUF. `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` is maintainer-confirmed. For 4B and 8B, `Voodisss/Qwen3-Reranker-{4B,8B}-GGUF-llama_cpp` and `gorse-io/Qwen3-Reranker-{4B,8B}-GGUF` hold Q8_0 files converted with the official script, not maintainer-checked. The test pod checks each file before its hash is pinned.

Decision: the smallest change that keeps architecture invariant 11 (one new file plus one `register()` line, no branch on strategy names):

1. New file `src/omrs/core/retrieval/reranker_llamacpp.py`, class `LlamaCppReranker`, `backend_name = "llamacpp"`. Same public surface as the ONNX and torch backends: `rerank(query, results, top_k)` and `last_failure_reason`. It sends one `POST {router}/v1/rerank` per query with the model name, the query and the candidate texts, reads `results[].index` and `relevance_score`, sorts, truncates to `top_k` and sets `_reranked`. Scores are mapped to (0, 1] as the `reranker-backend-selection` spec requires; whether the server returns a probability or a raw logit is pinned by a test from the pod check. An unreachable router, an unknown model or a bad reply returns the inputs un-reranked with `_reranked` false and a reason, and never raises.
2. One line in `registry.py`: `register("reranker_llamacpp", "omrs.core.retrieval.reranker_llamacpp:LlamaCppReranker")`.
3. `backend.py`: the map gains `"llamacpp": "reranker_llamacpp"`. `build_reranker_from_settings` calls `reranker_cls.from_settings(settings)` when the class has that class method, else today's `reranker_cls(model_id=...)`. Only the new class has it; it reads `retrieval.rerank_model` (the router model name) and `llamacpp_router_url`. This is duck typing, not a branch on names.
4. `src/omrs/config/rules.py:41`: accepted values `("onnx", "torch", "llamacpp")`.
5. The model is an entry in `llamacpp_models` with preset `embeddings: true`, `pooling: rank`, `ctx-size` 8192 and equal batch and ubatch sizes. The router loads it on demand by name. No new router role is needed; a test proves that a listed, unassigned rank entry raises no role problem.

Tests first (task group 12): registry and map resolution, the accepted value and the refusal of an unknown one, request shape and score order against a stub HTTP server, graceful failure, and both construction paths (`compose.build_reranker` and the lazy pipeline path) picking the backend.

Fallback, only if every 4B or 8B file fails the pod check: the existing `reranker_torch` backend with a sequence-classification conversion of Qwen3-Reranker, or a transformers backend that follows the model card recipe (the instruction prompt, then the softmax of the "yes" and "no" logits of the last token). Cost: the `torch` extra on the pod (ADR-073 allows it), about 16 GB of VRAM for 8B in bf16, which cannot share a 24 GB card with the 8B embedder, and a model outside the llama.cpp pin, recorded in the runtime manifest. That is a plan amendment and an operator decision, not a default.

### D28. Setups and settings in the harness (redesign, 2026-11-12)

- `arms.py` becomes a setup table built from the four factors. A setup has `embedder`, `chunk_size`, `reranker` (`off`, `0.6b`, `4b`, `8b`) and `hybrid`, and derives its name `e<embedder>-c<chunk>-r<reranker>-h<hybrid>`, its index `e<embedder>-c<chunk>` and its collection `exp35_<dataset>_e<embedder>_c<chunk>` (dots removed). `run_arms.py` takes `--setup NAME|all` and `--index NAME` in place of `--arm`. The old six arms, `env_overrides` (only `chunking-off` used it) and Granite Guardian leave the table. `JUDGE_NAMES` becomes `clef_flash, chat`.
- `settings_values` writes, per setup: `chunking.chunk_size` and `chunking.markdown_chunk_size` equal to the level, `chunking.chunk_overlap` at 15% (77, 154, 307); the Qwen3 tokenizer identity; `retrieval.rerank_backend: llamacpp` and `retrieval.rerank_model` (the router model name) for reranker-on setups; `retrieval.hybrid_sparse_backend: bm25` for hybrid-on setups. `rerank` and `hybrid` stay call arguments, as today. `router_env.check_resolved` refuses an environment or `.env` override of any of these keys. The trace settings record them.
- The router lists the embedder and, for reranker-on setups, the reranker. `llamacpp_router_models_max` is 2 in search and answer stages with a reranker, so a query embedding and its rerank never swap models. The D24 VRAM check decides whether this fits on the chosen GPU.
- Plan roles gain `reranker-0.6b`, `reranker-4b` and `reranker-8b` (Exp 35 task 4A.3).
- The `documents` profile stays the collection profile. Its only effects here are `chunking.strategy_fallback: markdown` and `top_k` 10; its `rerank_enabled` and `hybrid_enabled` are overridden by the call arguments. Setup names never use the profile name.

### D29. Datasets and the number match (redesign, 2026-11-12)

- Legal RAG Bench loader in `datasets35.py`: `qa` and `corpus` configs, split `test`, pinned HF revision and file SHA-256. Each passage is written once as `<id>.md` holding the title, the text and the footnotes when present; gold is `relevant_passage_id`. Questions keep the frozen seeded order.
- BioASQ and Legal passages as `.md` (operator decision, 2026-11-13): `datasets35.py` writes `<id>.md` in place of `<id>.txt` (today `datasets35.py:293-296`). The passages hold no headings, so the Markdown path makes one section per passage and splits it with the pinned Qwen3 tokenizer through `markdown_chunk_size`; the only change from `.txt` is the token counter (Qwen3 in place of the LlamaIndex default cl100k). The writer escapes a `#` at the start of any line so no text reads as a heading. The gold mapping strips the suffix, so gold ids do not change.
- FreshStack (operator decision, 2026-11-13): the loader drops the 20 Experiment 9 continuity queries (203 remain) and the corpus drops the 15 continuity documents and the overlay runbook. The harness references that add them leave `datasets35.py`: the `_FS_OVERLAY` and `_FS_OVERLAY_ID` constants and their SHA-256 entry (`:42-43`, `:62`), the overlay id mapping (`:221`), and the `continuity/*.md` glob and overlay append (`:262-263`). A new corpus tree hash is recorded at the freeze.
- Token-count check: one test ingests a small fixture of each of the four datasets at each chunk size and asserts that every chunk's Qwen3 token count is at most the level, that the splitter path is the model-token-aware Markdown path, and that the cl100k counter is never called.
- FinanceBench number match in `scoring35.py` (or a new `numbers35.py` if `scoring35.py` nears 500 lines): extract numbers with their scale words and signs, normalise thousands, millions, billions, percent, currency and parentheses, and pass when every reference number matches after rounding to its decimal places or within 1% relative difference.

### D30. Answer context budget (redesign, 2026-11-12; one round, 2026-11-13)

**Revision (operator decision, 2026-11-13): one round.** Every answer setup sets `answer.context_window` to 131,072 characters and `answer.max_rounds` to 1. The round budget is 131,072 minus 2,048 (reply) minus 1,536 (template) = 127,488 characters. The largest evidence set is 10 chunks of up to 2,048 Qwen3 tokens, at most about 92,000 characters, so every answer is one call. The prompt is then about 35,000 tokens at most. The answer model's context length on the pinned OpenRouter host is read from the models API and recorded in the protocol before the freeze; it must be at least 65,536 tokens, else the freeze stops. A test fails if any answer setup's largest evidence set needs more than one round. The text below is the earlier, multi-round plan; its recording of rounds and truncation stays.

At 2,048 tokens x `top_k` 10, the evidence is about 20,000 tokens (70,000 to 80,000 characters). With the defaults (`context_window` 8,192 characters, `max_output_tokens` 2,048, 4 rounds), the natural round budget is 4,608 characters, so OMRS widens each round to about 20,000 characters to fit the evidence into 4 rounds (`synthesis.py:169-189`), well under the 262,144-character ceiling.

- A test, run before the freeze, takes the question with the most evidence characters from each answer setup's search output and synthesises it through a recording stub seam with the frozen answer settings. It passes when no round raises the "available context size was not non-negative" error, and records the rounds and any truncation.
- Each answer row records `completion_calls` (rounds), the evidence characters and the truncation: the harness re-runs OMRS's own fit function (`_fit_and_measure`, a pure function) on the same rows and settings and counts truncated nodes and characters dropped. No OMRS change is needed. The report counts truncated answers per setup.
- (Answered 2026-11-13: one round, see the revision above.)

### D33. Answer correctness and its hand-label check (operator decision, 2026-11-13)

- The Ragas stage (D6) adds a fifth metric: `AnswerCorrectness` from `ragas.metrics.collections`, Ragas 0.4.3, called as `ascore(user_input=question, response=answer, reference=reference_answer)`. It needs the LLM (the frozen judge `openai/gpt-oss-120b`) and embeddings (the local 4B embedder, as for `AnswerRelevancy`). Weights stay at the library default (factual 0.75, similarity 0.25) and are written into the protocol. References come from each dataset's `answer` field (FreshStack: its reference answer). A question without a reference is recorded as not judged.
- Hand-label check before the metric counts: `correct35.py sample` draws 100 answers with seed 20261113 from the main run's half B (A2, D35; was the test pod session's answers), 25 per dataset, spread evenly over the three chunk sizes. A labelling page (as in task 8.4) shows the question, the reference and the answer, with no Ragas score, and records correct or not correct. `correct35.py agree` binarises the Ragas score at 0.5 (fixed before labelling) and gives Cohen's kappa (`cohen_kappa`, task 8.8) per dataset and pooled. At pooled kappa of at least 0.60, correctness is an H8 outcome; below, it is exploratory.
- Cost: about 3 more calls per answer without the contexts, about $0.0004 and 23 s per answer (estimate; measured in the test pod). Ragas goes from $83 to about $100, and the replicate pods from about 59 h to about 65 h each.
- The FinanceBench number match (D29) stays as a deterministic second check.

### D34. One search run per setup (operator decision, 2026-11-13)

Each of the 72 search setups runs once (run 1). Query-time retrieval on a sealed index is deterministic: the FreshStack smoke rerun (ADR-119, `fs-rerun/`) gave the same ranked lists, and G1 re-checks it on the three replicate pods for the 12 answer setups. The part that can vary, index building, is covered by the G2 rebuild check (D20). Three search runs would add about 194 pod hours and no statistical information.

### D31. Selection rule and factorial analysis (redesign, 2026-11-12)

- `select35.py` reads the saved search scores (Mac only, saved files) and applies the pre-registered rule: pooled score = plain mean of the four per-dataset mean nDCG@10; smallest embedder within 0.01 of the best (inclusive), then smallest reranker size within 0.01 at that embedder; equal scores pick the smaller size. It writes `selection.json` with every pooled score. Tests cover a gap of exactly 0.01, a tie and a missing setup (refused).
- `factorial35.py` builds per-question marginal scores and runs the contrasts of H1 to H8 with the existing `paired_permutation`, `paired_bootstrap`, `holm`, `wilson`, `mcnemar_exact` and `min_detectable_effect`. It adds no statistics function. Tests plant a known effect in a fixture and check that only that contrast counts, that Holm runs within one dataset, and that a wrong-sign result does not count.

### D32. Parallel index builds and search (operator instruction, 2026-11-12)

The 9 indexes (3 embedders x 3 chunk sizes) are independent, so they build on 9 parallel pods of the chosen GPU type, before the replicate pods start.

- Each index pod builds one index for all four datasets. It writes to its own LanceDB store on the network volume, `<out>/stores/<index>/lancedb`, so no two pods ever write one store (each store has its own metadata). Router state and scratch settings go to the pod's `--local-dir` (D7).
- After its ingest, the pod seals its own index: the fingerprint moves from `<out>/<dataset>/index-fingerprint.json` to `<out>/<dataset>/<index>/index-fingerprint.json`, one per index. Then the same pod runs its index's 8 search setups (4 reranker levels x 2 hybrid levels), read-only, as run 1.
- The rebuild check (D20) runs on a tenth pod, or on the `e4b-c1024` pod after its search, into a separate store.
- The GGUF files sit on the network volume once, so each pod loads them without a new download.
- Wall time on a 4090: about 4 h for the slowest build (8B, all four corpora) plus up to about 14 h of search on a 2,048-token index (three reranker sizes, both hybrid levels): about 18 h for the whole build and search phase, against about 133 h on one pod. Pod hours stay about the same, plus about 0.5 h of start-up per pod (D23).
- Then on the Mac: score the search stage and apply the selection rule (D31). Then the three replicate pods (about 65 h each, D22). End to end, about 4 days of pod wall time.

### D35. Methods-review fixes in the harness (pre-freeze amendment A2, 2026-11-13)

Decided by the operator on 2026-11-13 (A2c, D37, revises parts of this section): `statsmodels` in the `stats` dependency group; FinanceBench first-page credit with "any page" as a sensitivity column; token-matched answer setups at reranker on and hybrid on; the answer model stays `deepseek/deepseek-v4.1-flash-1017` on the API (Exp 35 design D0.12). Oracle retrieval came later the same day as an oracle run (D36).

The operator approved every fix of an independent methods review (Exp 35 change design D0.12). Harness consequences:

- **Unit scorer (B1).** `scoring35.ranked_units` changes from "cut 10 chunks, then map" to "map, keep first occurrence of each unit, then cut 10 units" (`scoring35.py:39-51`). Search stages save the top 100 chunks: `top_k` 100 and `fetch_k` 100 for the search call (A2c N1: without `fetch_k`, `policy.py:63-67` would size the rerank pool at 300), and the reranker returns the whole 100-candidate pool in its order. FinanceBench page credit is the chunk's first page; the "any page" credit (today's `scoring35.py:49-50`) is kept only as a sensitivity column. New secondary metric `evidence_recall_20k`: share of gold units in the chunks taken in rank order until their real Qwen3 token total reaches 20,480 (A2c N2; the crossing chunk is kept whole). The answer stage still sends 10 chunks in the 12 main setups; the token-matched setups send chunks up to the same 20,480-token budget, taken from the same saved list.
- **Setups (M5).** Two token-matched answer setups, `c512-t20k` and `c1024-t20k`, at the chosen embedder and reranker size, reranker on and hybrid on; the setup name gains `-t20k` when evidence is cut by the token budget instead of 10 chunks. 14 answer setups in all.
- **Closed-book run (M6).** A `closedbook` stage: one run, all 1,160 questions, the answer model with no evidence (a fixed prompt that asks for an answer from the model's own knowledge), then `AnswerCorrectness` and the number match. It runs on replicate pod 1.
- **Split halves (M3).** `split35.py` writes `halves.json` per dataset (seed 20261115). `select35.py` reads half A only. The report reads half B for answer-stage headlines.
- **Mixed model (M2; p-values revised by A2c N4, D37).** `experiments/_lib/stats_mixed.py` wraps `statsmodels` `MixedLM` for estimates, and `GEE` with cluster-robust errors for contrast p-values; (formula `ndcg10 ~ C(embedder)*C(chunk)*C(reranker)*C(hybrid)`, random intercept per question, REML) and returns planned contrasts with standard errors. It adds `statsmodels` as a PEP 735 dependency group `stats` in `[dependency-groups]` of `pyproject.toml`, the same mechanism as the `ragas` group; never an extra and never in the app install; `dev` includes it with `{include-group = "stats"}` so the fast suite runs its tests (decided by the operator, 2026-11-13), version pinned in `uv.lock`. The `AGENTS.md` hard boundary on new dependencies is met: the operator decided this on 2026-11-13. The experiments rule "use `_lib/stats.py`, write no new statistics code" is kept by calling the library, not writing an estimator; the wrapper is tested against a fixture with a known effect.
- **Labelling (M4).** One labelling page for three sets (claim kinds, faithfulness verdicts, correctness), labeller id `L1` or `L2` chosen on the page, never a name. `labels35.py` draws the samples (seeds 20261112, 20261116, 20261113), the L2 subsets (30%, seed plus 1), and computes kappa with bootstrap intervals (`cohen_kappa` and `paired_bootstrap` resampling).
- **Provenance (M7).** Each hosted call row records `model_returned` and `provider_returned` from the reply (OpenRouter `model` and `provider`; Z.AI `model`), beside the requested values. The join counts differences per role.
- **Reranker check (M8).** `rerank_check35.py` scores 200 seeded pairs (seed 20261117) per size with llama-server and with the transformers recipe, and reports Spearman correlation; below 0.95 the file is not pinned.

**Cost (A2), on an RTX 4090 at $0.89 per hour.**

| Change from A1b | Pod hours | Hosted |
| --- | ---: | ---: |
| Depth 100 retrieval with `fetch_k` 100 passed, so the rerank pool stays 100 (without it, 300 and three times the rerank hours); dense and hybrid top 100 cost seconds | about 0 | $0 |
| Two token-matched answer setups (6,960 answers at 2,048-level context: answers, five Ragas metrics, classifier; judges and Ragas on the replicate pods) | +36 (about +12 per replicate pod) | +$47 |
| Closed-book run (1,160 short answers plus correctness) | +1 | +$3 |
| Human labels (400 L1, 120 L2) | 0 | $0 |
| **A2 total** | **about 378 pod hours, about $350 with the volume** | **about $290** |
| Oracle run (D36) and A2c (no cost) | +4 | +$8 |
| **Final total** | **about 382 pod hours, about $354 with the volume** | **about $298** |

Final estimate after the oracle run and A2c: about **$650**, ceiling **$975** (1.5 x); see D37. At 3 times slower reranking than assumed, about $870. Replicate pods run about 77 h each.

### D36. Oracle run (approved 2026-11-13)

**Oracle run (approved by the operator, 2026-11-13).** One oracle answer run (run 1 only) on all 1,160 questions: the answer model `deepseek/deepseek-v4.1-flash-1017` with the same prompt and settings as the main answer setups, and the gold units given directly as evidence, with no retrieval. Sources: Legal RAG Bench, the gold passage; FinanceBench, the gold evidence page text(s) from the PDF as read by `pdf_inspector`; BioASQ, the gold passages (the corpus abstracts named by the question's relevant passage ids), because these are the units retrieval is scored on and they come from the same text the index holds, while snippets are fragments that a real retriever never returns; FreshStack, the gold documents, capped at the token budget of the largest main answer setup (about 20,480 Qwen3 tokens), with any truncation recorded per question as data. It is scored with the same Ragas `AnswerCorrectness`, GLM-5.3 and Clef-Flash claim checks and FinanceBench number match. Reported beside the closed-book run as floor (closed-book) and ceiling (oracle), descriptive only, no hypothesis test. Caveat: the oracle evidence has no distractor passages, so it is an upper bound, not a fair comparison with retrieval. Cost: about $8 hosted and about 4 pod hours on replicate pod 1. New estimate about **$650**, ceiling **$975** (1.5 x). The `oracle` stage builds contexts with `oracle35.py` and runs on replicate pod 1 after the closed-book stage.

### D37. Second methods review (pre-freeze amendment A2c, 2026-11-13)

**Pre-freeze amendment A2c (2026-11-13): second methods review.** It wins over D0.12 where they differ.

- **N1. Rerank pool stays 100.** With `top_k` 100 for depth-100 scoring, OMRS would size the rerank pool as max(`rerank_max_fetch`, `top_k` x `rerank_fetch_multiplier`) = max(100, 300) = 300 (`src/omrs/core/retrieval/policy.py:63-67`, `settings.py:61-62`). The harness passes `fetch_k=100` to `Engine.search` (it reaches the existing `fetch_k_override`, `pipeline.py:279-284`), so every reranker setup scores a pool of exactly 100 and returns all 100 in order. Dense and hybrid setups also fetch 100.
- **N2. Equal evidence by real tokens.** The equal-evidence metric `evidence_recall_20k` and the two equal-text answer setups no longer cut by chunk count. They take chunks in rank order and add each chunk's real Qwen3 token count to a running total; a chunk is included when the total before it is below 20,480; the chunk that crosses the limit is included whole (so the evidence is at most one chunk over 20,480), and no later chunk is. Short documents and short last chunks therefore no longer under-fill the budget. The setup names become `c512-t20k` and `c1024-t20k`; the `c2048` x 10 comparison is cut by the same rule.
- **N3. H6 endpoint on FinanceBench.** First-page credit penalises big chunks. H6 on FinanceBench is tested on `evidence_recall_20k` (gold pages within the 20,480-token evidence), its confirmatory endpoint for H6. nDCG@10 with first-page credit and with any-page credit are sensitivity results. H6 counts on FinanceBench only if the 20k measure supports it, and the report gives whether the two page rules agree in sign per contrast. FreshStack keeps unit-level nDCG@10 for H6.
- **N4. p-values from cluster-robust errors.** The mixed model with a random intercept per question stays for estimates and description. Each planned contrast's p-value comes from a GEE with the same mean model (`statsmodels` `GEE`, Gaussian, exchangeable working correlation) and cluster-robust standard errors clustered by question; on FinanceBench clustered by document. Holm runs across the contrasts of each dataset. The paired permutation test, or on FinanceBench the document-grouped bootstrap, is the pre-registered sensitivity check.
- **N5. H8 on all questions.** The selection rule averages over chunk size, so choosing on half A barely biases the chunk-size contrasts. H8 is tested on all questions. Descriptive headline answer numbers stay on half B.
- **Minor.** Only nDCG@10 is primary (the tolerance line names the others as secondary). FreshStack's reference answer is `answer_text` of `freshstack/queries-oct-2024`, config `langchain` (the accepted Stack Overflow answer). Oracle evidence is capped at 20,480 Qwen3 tokens for every dataset (FinanceBench, BioASQ and FreshStack; a Legal passage is at most 512), with truncation recorded. The one-round test covers the oracle and closed-book stages too. Floor (closed-book) and ceiling (oracle) are single runs, while main setups average 3 runs; the report says so. The report adds a per-question cross-table on retrieval misses: closed-book correct or not against RAG correct or not. Oracle retrieval is now part of the plan (an oracle run, approved 2026-11-13).
- **Cost.** N1 to N5 add no pod hours or calls (the pool stays 100). Final estimate: about **$650** (pods and network volume about $354 for about 382 pod hours, hosted calls about $298), ceiling **$975** (1.5 x).

Harness consequences: `run_arms.py` passes `fetch_k=100` on every search and answer retrieval; `scoring35.py` gains a token-budget cut (`evidence_by_tokens(chunks, budget=20480)`, Qwen3 counts from the pinned tokenizer); `answers35.py` builds `c512-t20k`, `c1024-t20k` and the 2,048 comparison with the same cut; `stats_mixed.py` returns MixedLM estimates and GEE contrast p-values; `factorial35.py` uses `evidence_recall_20k` for H6 on FinanceBench and all questions for H8; `oracle35.py` caps every oracle context at 20,480 tokens.

## Risks / Trade-offs

- [Reranker GGUF files for 4B and 8B are third-party] → The test pod checks each file against the model card recipe before its hash is pinned. A failed file blocks the freeze for that size; the D27 fallback is an operator decision.
- [Rerank mode is slow on llama.cpp (issue #30422)] → The test pod measures throughput at each size. The D23 projection uses the measured rate, and the $975 ceiling stops the plan before the freeze when the projection passes it.
- [The 8B embedder and the 8B reranker do not fit together] → The D24 GPU rule only admits a GPU that holds both without swapping.
- [Nine pods write to one network volume] → Each writes its own store folder; the seal and the fingerprint prove that no stage wrote another pod's store.

- [The harness depends on the shape of the OMRS `rate_limited` record] → The record is in the OpenAPI contract and its test (D25). The harness test builds its 429 result through the real OMRS result builder, so a change of shape fails a test before a run.
- [The app fixes change shipped behaviour that other users see] → Both keep their old outcome on the common path: a rate limit is still status `error`, and a native query still serves fresh results or falls back to BM25. The live app is reinstalled after the merge (proposal Impact), and the docs drift check (task 0.8) updates the guides.
- [An existing collection loses its native ranking until the next ingest] → A collection that relied on the first query to build its index now gets BM25 with a warning that names the ingest remedy. The default backend is `bm25` and the live app sets none, so no live collection is affected today.
- [A `RateLimitStop` in the middle of one answer's claims repeats that answer's earlier claim calls on resume] → At most one answer per worker is affected. Its row is written only after the repeat, so no row mixes calls from two attempts.
- [Concurrency raises the paid spend rate and can trip OpenRouter's spend budget] → 402 is retried with backoff and then stops cleanly. The test pod session measures the 402 count. The budget ceiling checks (D23 revision, D35) bound the total.
- [Z.AI 5-hour usage window runs out mid-stage] → The bounded attempts stop the stage with code 5. `--resume` continues when the window resets.
- [Three pods read one network volume at the same time] → Read speed can drop. Retrieval is a small part of the stage time. The build pod times the recheck's search stage on the volume before the replicate pods start.
- [A replicate pod dies mid-stage] → `--resume` on a new pod continues from the pending and row files. The machine record shows both pods.
- [Ragas makes the replicate pods run about 28 h of their about 65 h each (D22 revision)] → Higher Ragas concurrency lowers it, within the rate limits that the test pod session finds. The budget checks (D23) use the measured time.
- [The pod image and `EXP35_POD_IMAGE` drift apart] → The pod-creation script passes one pinned value to both. A stage refuses a value without a digest.
- [The gate sample holds few refusals (about 8.5% of smoke claims)] → The sample takes half of each dataset from claims the old regular expression flags, and the scores are stratum-weighted. The report gives the refusal count in the sample beside the recall.
- [The H-CC amendment follows the smoke data] → The amendment is dated, gives its reason, keeps the all-claims result as a robustness figure, and states the smoke shift on FreshStack openly. (History: the 2026-11-12 redesign dropped H-CC; the claim-kind rule now stands on its own.)
- [A hosted classifier changes over time] → The kinds are saved once with the classifier version and never recomputed. The gate runs on the same pinned model and host as the main-run classification.
- [The test pod session's small indexes and 40 questions do not match main-run rates] → The build pod's cost re-check uses the real index hours. A main-run stage that meets rate limits stops cleanly and resumes.
- [Pod-specific CUDA numerics change retrieval across machines] → This is what G1 now measures across machines. A mismatch is a finding and is reported, never replaced by another run (`protocol.md` section 6).

## Migration Plan

0. Build and test the two app fixes (group 0, D25 and D26) first. The harness groups rely on them. After the merge, reinstall the live app with the locked constraints, on the operator's go.
1. Build and test the code (tasks 1 to 8) on the feature branch. The default behaviour stays serial-equivalent: concurrency 1 gives today's files.
2. Run the classifier gate (tasks 8.1 to 8.7). The classifier calls run on a 4090 pod; labelling and scoring run on the Mac.
3. Resolve and record the image digest (task 9.1).
4. Pre-freeze test pod session (task 9.2, D24): calibration and the first budget check against the $975 ceiling, reranker file checks and throughput, the VRAM check, build time per chunk size, the FreshStack recheck, and every new stage end to end once. Delete the pod. Then the GPU-choice timing on the L40S and the H100 (task 9.3), each after a price quote and the operator's go.
5. Write the procedure, the measured values, the GPU choice, the G2 stop rule and the budget with its ceiling into `protocol.md` (group 10).
6. At G7, freeze `protocol.md` and `plan.json` with the measured values.
7. Index pods (D32, 9 in parallel on the chosen GPU type): each builds one index for all four datasets, seals it and runs its 8 search setups. The `e4b-c1024` rebuild check (D20) runs beside them. A failed check stops here: find the cause, fix, build again. Then the FreshStack recheck on the real indexes with zero errors in every answer setup, scoring and the selection rule on the Mac (D31), and the budget re-check (D23). Above $975, stop and ask the operator.
8. Replicate pods: run 1, run 2 and run 3 of the 12 answer setups at the same time. Each pod runs answer (with its own retrieval), the two judges (`clef_flash`, `chat`), `ragas` and `claimkinds` on its own run.
9. Copy back, then on the Mac run only steps on saved files: `join35.py`, determinism, the refusal report and statistics.

Rollback: every option has a default that keeps today's layout and serial behaviour. Concurrency 1, no `--local-dir` and no `--index-from` give the current harness. The app fixes roll back by reverting their commits; neither changes stored data or settings.

## Open Questions

- **Does Ragas 0.4.3 score a non-committal answer 0 in `answer_relevancy`?** Task 7.5, an early implementation task, checks the source. The report states the result either way. Until then, nothing in the protocol or report claims that a refusal lowers a Ragas score (D16).
Resolved by the operator (2026-11-12): the hybrid arm pins BM25 (D8); a rate-limited claim judge is typed (D25 item 3a); an HTTP 402 with no `Retry-After` is its own kind, `out_of_credit` (D25 item 1); the wrong wording in "Existing collections are usable without re-ingestion" is fixed (D26 item 7).
