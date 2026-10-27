# Design: pipeline sweep on llama.cpp

## Context

See `proposal.md` for the reason. Current state that shapes the approach:

- Experiment 3 (`experiments/3-e2e-smoke-test-metadata-2026-05-20/`) holds 6 documents in `corpus/`: 4 PDFs (Kalai et al. 2025, Popat and Starkey 2019, Van Der Weel and Van Der Meer 2024, Ghazali al-Mustasfa) and 2 Markdown READMEs (`grep-ai`, `paper-search-mcp-cf`). Its 17 questions are written out in `results.md` only. It ran on Ollama (`qwen3-embedding:0.6b`, `qwen3:0.6b` for metadata), ChromaDB, dense search with the reranker, `top_k=3`. Result: Hit@1 17/17.
- Experiment 2 (`experiments/2-embedding-model-comparison-2026-05-19/`) has the same 6 files (byte-identical) and the same 17 questions in `ground-truth.json`, with `expected_source` per question. It ran dense search with the reranker off, on Ollama and ChromaDB. Results: `qwen3-embedding:0.6b` and `qwen3-embedding:8b` both Hit@1 17/17 and MRR 1.000.
- No earlier run on this set used a 4B embedding model. No earlier OMRS run used FinanceBench.
- `experiments/_lib/llamacpp_runtime.py` `verify_llamacpp_runtime(block, base_url=...)` reads one server. It checks every `llama.cpp` model in the `runtime` block against that one server and fails when the server does not list a planned file. `FoundRuntime.as_run_record()` holds one `build` and a `models` list.
- llama.cpp router mode (`llama serve`) runs several models behind one address and starts each with its own preset arguments. The live Llama app on this Mac runs this way: its embedding model has `--embeddings --pooling last`, its chat models do not. Task 3.4 of `reproducible-experiment-runtime` ran the live-server check against it in router mode and passed (`openspec/changes/archive/2026-10-27-reproducible-experiment-runtime/evidence/live-check.txt`). The check reads each model path from `GET /v1/models`, so one call covers every model.
- The OMRS llama.cpp embedding provider sends the model name with each request, so a router can route it.
- OMRS settings also address two llama.cpp servers: `llamacpp_embed_url` (default port 8080) and `llamacpp_chat_url` (default port 8081). The embedding provider `core/providers/embeddings/llamacpp.py` needs `uv sync --extra llamacpp`.
- The `documents` profile turns the reranker on and hybrid off. `defaults.yaml` sets `metadata.extraction_mode: llamaindex`, which calls a language model during ingestion. Claim checking (`answer.verify_claims`) is off by default and uses `verify_provider` (`cloud` by default, `local` for the local backend).
- The reranker is an ONNX cross-encoder. OCR engines run outside llama.cpp. ADR-103 leaves both on their current runtimes, under the runtime-manifest requirement.
- The FreshStack corpus is in `~/Development/DATA/omrs/experiments/<folder>/freshstack-corpus`. `prepare_freshstack.py` (Experiments 9a and 22, seed 20260530) builds the LangChain slice. FinanceBench is not downloaded yet.

## Goals / Non-Goals

**Goals:**

- Find every stage that breaks when Ollama is removed, before Experiment 35 freezes its plan.
- Give Experiment 35 measured embedding rates for 0.6B, 4B and 8B on the measurement Mac, and an estimate per corpus.
- Exercise the run-record path with the found runtime of a router that serves the embedding and the chat model.

**Non-Goals:**

- Measuring retrieval quality. The set is too small and too easy (Experiment 2 is at the ceiling). The scores only catch gross breakage.
- Ragas, statistics beyond Hit@1, MRR and Hit@page, and the publication rules.
- Moving the live app, CI or the tripwire baselines off Ollama.
- Changing any production default.

## Decisions

### D1. The fixed set

| Part | Content | Source |
| --- | --- | --- |
| Documents | The 6 files of Experiment 3 `corpus/` | Copied into the new folder's `corpus/`, SHA-256 in the protocol |
| Questions | The 17 questions of Experiment 2 `ground-truth.json` | Copied, SHA-256 in the protocol. Same set as Experiment 3, with Experiment 2's spelling |
| PDF arm | 5 FinanceBench PDFs and every open-sample question on them | Selection rule below |

FinanceBench selection rule: rank the documents of the open sample (`PatronusAI/financebench`) by question count, highest first, ties by document name. Take the first 5 with 200 pages or fewer. Freeze the 5 names, their SHA-256 and the question IDs in the protocol before the first run. The PDFs go in the gitignored `output/` (CC BY-NC 4.0). The harness converts the zero-indexed `evidence_page_num` once, and a test checks the conversion.

The FinanceBench questions add the real-PDF path (long 10-K filings, tables) that Experiment 3 lacks. Their Hit@page is reported as a first number, with no comparison.

Alternatives: Experiment 3 alone. Rejected, because its PDFs are short academic papers and do not test the filing layout of Experiment 35. A FreshStack slice in Part A. Rejected, because it is plain text and Part B already reads it.

### D2. Models and servers

| Role | GGUF | Server |
| --- | --- | --- |
| Embedding, Part A baseline | `Qwen/Qwen3-Embedding-4B-GGUF`, `Qwen3-Embedding-4B-Q8_0.gguf` | router |
| Embedding, Part B and comparison arms | `Qwen/Qwen3-Embedding-0.6B-GGUF` Q8_0, `Qwen/Qwen3-Embedding-8B-GGUF` Q8_0 | router, one model loaded at a time |
| Language: metadata, answer, claim check | `Qwen/Qwen3-4B-GGUF`, `Qwen3-4B-Q8_0.gguf` | router |

- All files are Q8_0, the 8-bit level that AGENTS.md Gotcha 16 asks for.
- The plan pins the SHA-256 of each file and one exact llama.cpp build: the build installed on the Mac on the day the plan is written (build 11671 was measured on 27 October 2026). Builds earlier than b11510 are not allowed (Gotcha 16).
- One `llama serve` router with one preset per model. Embedding presets: `--embeddings --pooling last --ctx-size 8192 --ubatch-size 8192`, as in the guide example. Chat preset: `--ctx-size 16384` (the OMRS `llamacpp_context_window` default). The plan records each preset as `server_args`. Answer and claim-check requests use temperature 0.
- The router listens on `127.0.0.1` on a scratch port that the live app and the live Llama app do not use (for example 18080). Both `llamacpp_embed_url` and `llamacpp_chat_url` point at it.
- The run sets `embed_provider=llamacpp`, `local_backend=llamacpp`, metadata language model `local`, `verify_provider=local`, and the LanceDB store inside `output/`. Settings go in a scratch `OMRS_CONFIG_DIR` inside `output/`. Nothing reads or writes `~/.config/omrs` or `~/.omrs`.
- `PDF_READER` stays at its production default, `pdf_inspector` (`defaults.yaml`), for every document. No other reader is used as a substitute, because a second reader would add a variable. The sweep runs after the change `pdf-inspector-page-provenance` merges, so pdf-inspector emits one document per page with `page` and `page_label`. The run records which reader ran for each file (the fallback chain may still pass a file to LiteParse or pypdf, as in production) and checks that every PDF chunk has a page number. It also measures whether per-page output changes retrieval on the 17 questions (Experiment 3 used whole-document pdf-inspector output under Ollama).
- Metadata extraction stays at its default (`llamaindex`, one language-model call set per chunk). The run records its time per chunk, so Experiment 35 can choose its mode with a measured cost.

Alternatives: `Qwen3-4B` at Q4_K_M for speed. Rejected by Gotcha 16. The Experiment 3 language model `qwen3:0.6b`. Rejected, because Experiment 35 needs a usable answer model and a 0.6B judge says little.

### D3. One router and the live-server check

The run calls the existing `verify_llamacpp_runtime(block, base_url=...)` once against the router. In router mode it reads every model path from `GET /v1/models`, hashes each planned file and checks the one build. `found.as_run_record()` goes to `record_run_start(HERE, runtime=...)`. No change to `experiments/_lib/` is needed.

Each Part B timing run is its own run, with its own run record and a plan block for the one embedding model it times.

Alternatives:

- Separate embedding and chat servers. Rejected: the check reads one server, so it would need a `files` filter and a helper that joins two results. Router mode already gives each model its own arguments, and the project ran the check against a router on 27 October 2026.
- Fallback: if the sweep finds that a router cannot serve both models correctly, it records the fault as a finding. Separate servers and the code they need then become a follow-up change.

### D4. Part A run order

1. Hash every input file and compare with the protocol. Stop on any difference.
2. Start the router. Run the live-server check (D3). Call `record_run_start`.
3. Ingest the 11 documents through `Engine` with the 4B embedding model. Record per file: reader, OCR routing decision, normalisation applied, chunk count, error count.
4. For each of the 17 + FinanceBench questions, search in `dense`, `hybrid` and `hybrid + reranker` with `top_k=10`. Save the ranked chunk IDs and sources.
5. Answer each question twice: with `verify_claims` off and on. Record status, latency and token use. Answers are not scored for quality.
6. Repeat step 4 in a new process on the same index (the determinism check). Compare chunk IDs and order exactly.
7. Comparison arms: rebuild a dense index of the 6 Experiment 3 documents with 0.6B and with 8B, and run the 17 questions dense with the reranker off. This matches Experiment 2's conditions except the store (LanceDB, not ChromaDB) and the runtime.

Each step writes a JSONL file in `output/`. A failure in one item is recorded and the run continues, so one run lists every broken stage.

### D5. Exit rule and tolerance

The plan states these before the first run:

| Check | Pass |
| --- | --- |
| Stages | Every stage and every search and answer mode has zero errors |
| 0.6B dense, 17 questions | Hit@1 at least 16/17 and MRR at least 0.94 (Experiment 2: 17/17, 1.000) |
| 8B dense, 17 questions | Same bounds (Experiment 2: 17/17, 1.000) |
| 4B dense with reranker (the `documents` profile), 17 questions | Hit@1 at least 16/17 (Experiment 3: 17/17, dense with reranker, `top_k=3`) |
| 4B hybrid, with and without reranker, 17 questions | Reported only |
| 4B dense, 17 questions | Reported only. No earlier 4B number exists on this set |
| FinanceBench | Reported only (Hit@page, Recall@10). No earlier number exists |
| Determinism | Every repeated ranking identical |

One miss in 17 moves Hit@1 by 0.059. The bounds allow one question to drop. Experiment 2 sits at the ceiling, so the comparison catches breakage, not small shifts.

Verdict: `PASS` when every row passes. `FAIL` otherwise, with the failing stage named. A failure is fixed (in a separate change if it touches `src/`) before Experiment 35 freezes its plan.

### D6. Part B: embedding timing and extrapolation

- Slices, one per corpus, so that document length is measured and not assumed:
  - FreshStack: the first 200 documents, by sorted document ID, of the LangChain corpus built by `prepare_freshstack.py` (seed 20260530).
  - BioASQ: the first 200 passages, by sorted passage ID, of the `enelpol/rag-mini-bioasq` test-split corpus at a pinned revision.
  - FinanceBench: the 5 PDFs of D1, read once in Part A. Part B embeds their saved chunks, so reader time is not mixed into the rate.
  - The protocol records the hash of each ID list.
- For each model (0.6B, 4B, 8B): start the server, run the live-server check, embed one warm-up batch (not timed), then chunk and embed each slice through the OMRS ingestion path with the `documents` profile settings. Record wall time, input tokens (from the server's `usage.prompt_tokens`) and the server's peak resident memory (sampled every 0.5 s). Stop the server before the next model. One model runs at a time.
- Extrapolation: estimated time = corpus tokens / tokens per second measured on that corpus's slice. Metadata extraction time per chunk, measured in Part A, is extrapolated the same way and reported in its own column. The Qwen3 embedding models share one tokeniser, so each corpus is counted once:
  - FreshStack (10,024 documents) and BioASQ (40.2K abstracts): chunk every document and count tokens with the server's `/tokenize` endpoint. No embedding.
  - FinanceBench: tokens per page from the 5 Part A PDFs, times the total page count of all PDFs the 150 open questions cite (page count from pypdf).
- The report gives one table: model by corpus, estimated hours, and the peak memory. It names the output file of each number.

The sweep does not decide local or cloud. Experiment 35 compares these estimates with its Mac budget (its task 1.7).

### D6a. Part C: fast mode against exact mode, and the pinned presets

Speed settings in llama.cpp can change the output a little. Batching several inputs together (`--parallel`, `--kv-unified`, concurrent requests) makes vectors depend on which inputs share a batch (llama.cpp issue #6950). Speculative decoding and the prompt cache can change generated text. The research note of 27 October 2026 found these in build 11671 (`common/arg.cpp`, `tools/server/README.md`).

Presets (every value written out, so no default can change silently):

| Model | Preset |
| --- | --- |
| Embedding, exact | `embeddings pooling=last embd-normalize=2 ctx-size=8192 batch-size=8192 ubatch-size=8192 parallel=1 kv-unified=false flash-attn=on n-gpu-layers=all fit=off cache-type-k=f16 cache-type-v=f16` |
| Embedding, fast | As exact, but `parallel=8 kv-unified=true`, and the client sends 8 requests at a time |
| Chat (Qwen3-4B) | `ctx-size=16384 parallel=1 flash-attn=on n-gpu-layers=all fit=off cache-type-k=f16 cache-type-v=f16 spec-type=none cache-prompt=false cache-reuse=0`; requests at temperature 0 with a fixed seed; the thinking setting pinned through `chat-template-kwargs` |

Notes from the research:

- Without `--parallel`, build 11671 uses 4 slots with a shared cache. So `parallel=1` is written out.
- `--fit on` (the default) can move layers to the CPU when memory is short. `fit=off` with `n-gpu-layers=all` keeps every layer on the GPU.
- `ubatch-size` must hold the longest chunk, or one input is split across batches.
- `--mlock` and `--no-mmap` no longer exist in this build. `--load-mode` replaces them.
- Open issue #30323 reports embedding mode about 1.55 times slower with Qwen3-Embedding. The sweep records the measured rate either way.

Part C method:

1. Use the 4B model and the three Part B slices.
2. Run exact mode, then fast mode, in fresh router starts. Sort inputs by chunk ID in both.
3. Compare each vector pair. Report the lowest and the median cosine similarity.
4. Build a dense index from each run's vectors for the 17-question set and the FinanceBench questions. Compare the rankings and nDCG@10.
5. Record the speed of each mode.

Rule, stated before the run: fast mode is allowed for Experiment 35 when the lowest cosine is at least 0.9999 and no ranking in the top 10 changes. Otherwise Experiment 35 uses exact mode. The report gives the speed gain and the measured drift either way.

The plan also records a `/props` snapshot, the start-up lines for `n_ctx_seq` and `flash_attn`, and that no `LLAMA_ARG_*` environment variable is set. It records the client settings: inputs per request, concurrency and input order.

### D7. Overlap with Experiment 35 task 1.4

Yes, they overlap. Experiment 35 task 1.4 (as read on 27 October 2026) plans: "Time local Qwen3-Embedding 0.6B, 4B and 8B (GGUF, same quantisation) on a fixed slice of each corpus. Record wall time, tokens and peak memory, and extrapolate to each full corpus. Reuse the `pipeline-sweep-llamacpp` timing when it exists for the same machine and files."

Part B does that task in full: the same three models, Q8_0, one slice per corpus, the same three measures and the extrapolation. Experiment 35 reuses the Part B numbers when its machine, GGUF files and build match the Part B plan, and does not time again. The local-or-cloud decision and the OpenRouter fallback stay in Experiment 35 task 1.5. This change does not edit Experiment 35.

### D8. Experiment folder

Created at apply time with:

`uv run --no-sync omrs experiments new pipeline-sweep-llamacpp --title "Pipeline sweep on llama.cpp" --category runtime --size Standard --purpose optimisation`

The command takes the next free number and skips the reserved numbers. Standard size gives `experiment.json`, `protocol.md`, `plan.json` and `report.md`. The `runtime` block in `plan.json` is a guide rule for `optimisation` (ADR-103 decision 9), but this sweep fills it in full, because it tests that path for Experiment 35.

## Risks / Trade-offs

- [A local 4B judge is slow; Experiment 20 found a local `qwen3:4b` judge not practical] → The sweep only checks that claim checking runs and records its time. Experiment 35 decides whether to keep a local judge.
- [The 5 FinanceBench PDFs are long and slow to read] → The 200-page cap in D1. Reader time per file goes in the output.
- [Text-born PDFs may send no page to OCR, so the OCR engine is not exercised] → The report states which routing decisions occurred. An OCR-engine test is not in scope.
- [The router and the 8B model use much memory] → Part A keeps 4B embedding (about 4.3 GB) and 4B chat (about 4.3 GB) loaded together. Part B loads one model at a time. Tell the user before the router starts (heavy-run rule).
- [The 17-question set sits at the ceiling] → Accepted. The scores catch breakage only (Non-Goals).
- [LanceDB, not ChromaDB, in the comparison arms] → Named in the report as a known difference from Experiments 2 and 3.
- [The ONNX reranker may not be fully deterministic across processes] → The determinism check covers it. A difference is reported, not hidden.

## Migration Plan

1. Create the folder, write and commit `protocol.md` and `plan.json`, then run.
2. Rollback: delete the new folder. No record outside it changes.

## Open Questions

- The exact llama.cpp build and the SHA-256 values are read on the day the plan is written. They do not change the approach.
