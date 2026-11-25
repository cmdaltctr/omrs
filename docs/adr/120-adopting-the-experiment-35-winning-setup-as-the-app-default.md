# ADR-120: Adopting the Experiment 35 Winning Setup as the App Default

- **Date:** 2026-11-25
- **Status:** Proposed (the decision is completed after the Experiment 35 results; accepted only then)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-018](018-balanced-retrieval-defaults.md), [ADR-063](063-model-token-aware-markdown-chunking.md),
  [ADR-065](065-ocr-fallback-gate-promoted-to-packaged-default.md), [ADR-119](119-experiment-35-model-matrix-and-claim-checker.md),
  experiment `experiments/35-full-rag-benchmark-2026-11-01/`, change `exp35-main-run-readiness`

## Context

Experiment 35 measures the OMRS pipeline on four public benchmarks over four factors: embedder size,
chunk size, reranker and hybrid search. The harness builds a real OMRS `Engine` through
`compose.build_engine()`. Every ingest, search and answer goes through `Engine.ingest`,
`Engine.search` and `Engine.answer`. So the reader, chunker, embedder, store, BM25, fusion,
reranker call, answer prompt and citation parser are the app's own code.

The harness does not run the app defaults. It writes a scratch `omrs.jsonc` for each setup with
pinned values from `plan.json`, and it adds experiment-only steps. A read-only audit on 2026-11-25
compared the harness with the app, step by step, with file and line evidence (DATA
`experiments/35-full-rag-benchmark-2026-11-01/harness-vs-app-audit-2026-11-25.md`).

After the results, the owner wants the best setup to become the app default. That is only safe when
each difference between the measured setup and the app is known. Some differences are settings the
app can take. Some are measurement steps that must stay in the harness. Some cannot be adopted and
must be stated in the paper so a reader knows what was measured.

Four audit items needed a decision before the freeze. The owner approved all four on 2026-11-25:

1. **OCR during ingest (fixed).** Protocol section 4.3 decided no OCR of source pages, but the
   harness wrote no OCR key, so the app default (OCR fallback on) ran during the FinanceBench test
   ingest. Now `plan.json` pins `ocr_fallback_enabled` false and the harness refuses a run where it
   resolves on (`plan.json` amendment A6).
2. **Answer output cap (fixed).** `answer.max_output_tokens` 2,048 was pinned but OMRS only uses it to
   size the prompt budget. The Experiment 35 path now sends it as `max_tokens` and records each
   reply's finish reason (amendment A7). The app's own answer path is unchanged.
3. **Hybrid search depth (recorded, no code change).** The harness fuses 100 dense and 100 BM25
   results, cuts the fused list at 100, then keeps the first 10 (`plan.json`
   `pins.recorded.hybrid`). The app with the reranker off fetches 10 per side and cuts to 10
   (`src/omrs/core/retrieval/policy.py`, `fetch_k = top_k`). The experiment defines hybrid at
   depth 100.
4. **Source metadata in the answer prompt (recorded, no code change).** Each source in the answer
   prompt carries its file path and name and its retrieval score (`src/omrs/core/answer/evidence.py`,
   LlamaIndex `MetadataMode.LLM`). FinanceBench file names give the company and the year. The app
   does the same by design.

## Decision

To be completed after the Experiment 35 results. This record fixes the rules now, so the choice
cannot follow the results.

1. **Only measured settings become defaults.** A default changes only to a value that a measured
   setup used. A value the experiment did not measure (for example the four-round refine path, or
   metadata extraction on) stays as it is, and this record names it as not measured.
2. **Which defaults change (to complete).** Name the winning setup and, for each row marked "adopt"
   below, the new value and where it lives: the global default (`src/omrs/config/`, the
   `Settings` model and `defaults.yaml`) or the `documents` profile
   (`src/omrs/config/profiles/documents.yaml`). The `codebase` profile does not change, because no
   benchmark measured code folders as the app chunks them (the FreshStack export fences code rows
   and uses the Markdown splitter).
3. **Hybrid depth.** If a hybrid-on, reranker-off setup wins, the app pool rule must change to the
   measured depth (100 per side, fused cut 100) before the default changes, or this record states
   that the app result is not the measured one. A hybrid default also needs the `hybrid` extra
   (`rank_bm25`, `nltk`) in the install.
4. **Re-ingest rule for live collections (to confirm).** A default that changes the stored chunks or
   vectors (embedder, chunk size, chunk overlap, tokenizer, metadata extraction, OCR, PDF reader)
   applies to an existing collection only after a full re-ingest that the user starts. OMRS must not
   mix old and new chunks in one collection. A default that changes only search or answering
   (reranker, hybrid, answer settings) applies at the next query with no re-ingest.
5. **OCR and the output cap stay as the app has them** unless a separate change says otherwise. The
   experiment ran with OCR off and a sent output cap, so its results say nothing about the app's OCR
   default or about an app-side cap.

## Harness against app: every difference

Markings: **Adopt** (the app default takes the winner's value), **Harness-only** (stays an
experiment step), **Paper** (the paper's methods must state it). A row can carry more than one.
Rows where the harness and the app run the same code with the same value, and the paper needs no
sentence, are left out (profile name, embedding batch, exact vector search, RRF constant 60, score
threshold 0.0, rerank decision, client timeout and retries, concurrency, query cache, citation
parse, evidence order). File and line evidence is in the audit.

| # | Step | Experiment 35 harness | App default | Marking |
| --- | --- | --- | --- | --- |
| 1 | OCR during ingest (item 1) | Off, pinned and checked (fixed 2026-11-25, A6) | On: page OCR fallback, local `pp-ocrv6-small`, OCR worker for escalated pages | Harness-only; Paper. App default not measured |
| 2 | Answer output cap (item 2) | `max_tokens` 2,048 sent; finish reason per reply recorded (fixed 2026-11-25, A7) | 2,048 sizes the prompt only; no cap sent | Harness-only; Paper. An app cap needs its own change |
| 3 | Hybrid depth and cut (item 3) | 100 dense plus 100 BM25, fused cut 100, then first 10 | Reranker off: 10 per side, fused cut 10 | Adopt (pool rule) only if hybrid-on, reranker-off wins; else Paper and this record state the gap |
| 4 | Source metadata in the answer prompt (item 4) | Path, name and retrieval score per source | Same, by design | Paper. A change is a separate proposal |
| 5 | Settings check | Refuses a run when OMRS resolves a written key differently; unwritten keys not checked | Source order env, `.env`, `omrs.jsonc`, YAML | Harness-only; Paper (which keys are pinned) |
| 6 | PDF reader | `pdf_inspector`, pinned and checked | `pdf_inspector` | Paper (name and version) |
| 7 | FinanceBench corpus | One shared index per embedder and chunk size, no per-document filter | No filter unless the caller sets one | Paper |
| 8 | FreshStack export | One `.md` per distinct row, code rows in a Markdown fence, repeats removed | Code files go to the code splitter | Harness-only; Paper. No claim for raw code folders |
| 9 | BioASQ and Legal export | One `.md` per passage, line-start `#` escaped | Headings kept, `header_path` filled | Harness-only; Paper |
| 10 | Ingest granularity | One `Engine.ingest` per file, 600 s watchdog | Usually one call per folder | Harness-only |
| 11 | Store version history | Old Lance versions deleted every 64 files | Versions kept | Harness-only |
| 12 | Index seal and checks | Fingerprint, version, full-text stats, rebuild gate | None | Harness-only |
| 13 | Chunk size | `chunk_size` and `markdown_chunk_size` 512, 1024 or 2048 | 512 and 1024 | Adopt (winner, both keys) |
| 14 | Chunk overlap | 15 % of the chunk size (77, 154, 307) | 100 tokens at any size | Adopt with the chunk size, or state that the default keeps 100 |
| 15 | Token counter | Qwen3-Embedding-4B tokenizer `5cf2132a`; run refuses the legacy fallback | Same tokenizer; falls back to the legacy splitter with a warning | Adopt (tokenizer cached at install); Paper |
| 16 | Metadata extraction | Off | LLM title, keywords and summary, embedded | Paper. Default stays on only with a "not measured" note |
| 17 | Embedded text | Chunk text plus `file_name` and `header_path` | Same rule | Paper (FinanceBench names hold company and year) |
| 18 | Embedder | Qwen3-Embedding 0.6B, 4B or 8B, Q8_0, SHA-256 pinned | Qwen3-Embedding-4B Q8_0 | Adopt (winner, file SHA-256); re-ingest rule applies |
| 19 | Embedder server preset | No `embd-normalize`, `parallel`, `kv-unified` | Adds `embd-normalize 2`, `parallel 1`, `kv-unified false` | Adopt the shipped preset after one check of equal vectors on 20 chunks |
| 20 | Query instruction | Empty | Empty | Paper |
| 21 | Search depth | `top_k` 100, `fetch_k` 100, unassembled; first 10 used | `top_k` 10 | Harness-only (`fetch_k`, `unassembled` exist only on the Python Engine); Paper |
| 22 | BM25 | `rank_bm25` 0.2.2, Porter stems, k1 1.5, b 0.75 | Same code; needs the `hybrid` extra | Adopt the extra in the install if hybrid is adopted |
| 23 | Reranker | Qwen3-Reranker 0.6B, 4B or 8B on llama.cpp; a failed rerank stops the stage | ONNX MiniLM cross-encoder; a failed rerank falls back to the first order | Adopt (backend, size, SHA-256); Paper. Fallback path not measured |
| 24 | Reranker instruction | Fixed llama.cpp Qwen3 template, recorded | OMRS sends no instruction | Paper |
| 25 | Context assembly | Private `assemble` on the kept head, no neighbour expansion | Same call inside `search()` | Harness-only |
| 26 | Evidence selection | 10 chunks, or a 20,480-token cut for `-t20k` setups | `top_k` chunks only | Harness-only. A token budget is a separate proposal |
| 27 | Answer entry | `Engine.answer(rows=...)` | `Engine.answer` runs its own search | Harness-only |
| 28 | Answer prompt | `GROUND_TEXT_QA_TEMPLATE`, one round, no refine | Same template, refine on later rounds | Paper |
| 29 | Answer model and host | `deepseek/deepseek-v4.1-flash-1017`, `deepinfra/fp8`, no fallback | llama.cpp, no model until the user picks one | Paper. The default model is a separate choice |
| 30 | Temperature and seed | 0 and seed 20261101 | Not sent (LlamaIndex 0.1, no seed) | Paper; adopt only by a decision here |
| 31 | Reasoning | `none` | Host default | Paper; adopt only by a decision here |
| 32 | Context budget and rounds | 131,072 characters, one round | 8,192 characters, four rounds | Adopt with the winner, or state that the four-round path was not measured |
| 33 | Rate limits and resends | Gate with waits, resend on `--resume`, third error closes as missing | One call | Harness-only; Paper (missing counts) |
| 34 | Claim checking | Separate stage, GLM-5.3 and Clef-Flash, own settings | Inline, off by default | Harness-only; Paper |
| 35 | Closed-book run | Own prompt through private `prepare_models` | No such mode | Harness-only |
| 36 | Oracle run | Gold pages through the private PDF reader | No such mode | Harness-only |
| 37 | Evidence measurement | Private fit and measure functions; metadata block not counted | Same functions in the answer path | Harness-only; Paper (which characters are counted) |
| 38 | Ragas, claim kinds, length check, determinism, refusals, RAGFlow | Experiment tools | None | Harness-only |
| 39 | FreshStack query text | Title, blank line, body | What the user types | Paper |
| 40 | Workspace profiles | Config and state folders moved; workspace not moved | Read-only catalogue | Harness-only |

## Paper methods: must state

1. The OMRS revision and the public calls used: `Engine.ingest` per file,
   `Engine.search(top_k=100, fetch_k=100, unassembled=True)`, `Engine.answer(rows=...)`. `fetch_k`
   and `unassembled` exist only on the Python Engine, not in the CLI, MCP or web transports.
2. Search depth: every setup ranks 100 candidates. Hybrid fuses 100 dense and 100 BM25 results and
   cuts the fused list at 100; the first 10 go to assembly and the answer. The app with the reranker
   off fuses 10 and 10, so a hybrid-on, reranker-off result is not what the app gives by default.
3. Chunking: the Markdown splitter for every corpus, sizes 512, 1024 and 2048 Qwen3 tokens,
   overlap 15 %, tokenizer Qwen3-Embedding-4B revision `5cf2132a` for all three embedders.
4. Corpus export: FreshStack code rows wrapped in Markdown fences and deduplicated by ID and text;
   BioASQ and Legal headings escaped; FinanceBench as one shared PDF index with no per-document
   filter.
5. The embedded text includes `file_name` and `header_path`. FinanceBench file names hold the
   company and the year. Metadata extraction was off.
6. The answer prompt carries a metadata block per source with the source file path and name and the
   retrieval score. FinanceBench paths name the company and the year. The app does the same.
7. No query instruction on the embedder; the reranker instruction is the fixed llama.cpp Qwen3
   template.
8. The answer model, host `deepinfra/fp8` with no fallback, temperature 0, seed, reasoning `none`,
   one completion round, a 131,072-character budget, and an output cap of 2,048 tokens sent as
   `max_tokens`. The number of replies cut at the cap (finish reason `length`) per setup.
9. OCR was off during every ingest (`ocr_fallback_enabled` false); no source page went to an OCR
   engine. The pre-freeze test pod answers (2026-11-24 and 2026-11-25) ran with OCR on and no
   output cap and are not results.
10. The resend and rate-limit rules, and how many questions closed as missing per setup.
11. The claim judges ran after answering, on saved answers, with their own settings (GLM-5.3
    reasoning `low`, temperature 0, seed; Clef-Flash local), not the app's inline verification.

The same list is in `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` section 8.

## Consequences

### Positive

- Each difference between the measured setup and the app has a written fate before the results
  exist, so the adoption cannot pick its rules after seeing the scores.
- The paper's methods list comes from the same audit, so the paper and the app default describe the
  same pipeline.
- The two unintended differences (OCR on, no output cap) were fixed before any main-run data.

### Negative

- Some measured settings cannot reach the app by a settings change alone: the hybrid depth rule, the
  20,480-token evidence cut and the fenced code export. Adopting a setup that depends on them needs
  code changes or a stated gap.
- The app keeps several values the experiment did not measure (OCR on, metadata extraction on, the
  four-round refine path, no output cap). The app result can differ from the paper's numbers.
- A new embedder or chunking default means a full re-ingest of every live collection that should
  use it.

### Neutral

- The prompt metadata block (path, name, score) is the same in the app and the experiment; any
  change is a separate proposal with its own evaluation.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **Adopt the whole harness configuration as the app default** | Several harness steps (fenced export, token cut, depth 100, sealed indexes, resend gate) are measurement tools, not app behaviour. Some have no app equivalent. |
| **Change the app to match the harness before the run** (OCR, output cap, hybrid depth) | Changes product behaviour with no measurement of the app side. The experiment pins its own values; the app follows only measured winners. |
| **Decide the adopted defaults after seeing the results, with no rules now** | The choice could then follow the scores. Fixing the rules and the markings before the freeze keeps the adoption honest. |
| **Do nothing; keep app defaults** | The benchmark result would then describe a pipeline nobody runs. |

## References

- Audit: DATA `experiments/35-full-rag-benchmark-2026-11-01/harness-vs-app-audit-2026-11-25.md`
- `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` section 7 (notes of 2026-11-25) and
  section 8 (methods statements)
- `experiments/35-full-rag-benchmark-2026-11-01/plan.json` amendments A6 and A7, `pins.settings`,
  `pins.recorded.hybrid`
- `experiments/35-full-rag-benchmark-2026-11-01/arms.py` (`settings_values`),
  `answers35.py` (`cap_answer_output`), `live35.py` (`LiveDeps.engine`)
- `src/omrs/core/retrieval/policy.py` (pool rule), `src/omrs/core/answer/evidence.py` (prompt
  metadata), `src/omrs/core/answer/synthesis.py` (prompt budget)
- [ADR-018](018-balanced-retrieval-defaults.md), [ADR-119](119-experiment-35-model-matrix-and-claim-checker.md)
