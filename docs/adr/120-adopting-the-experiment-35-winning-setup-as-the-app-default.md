# ADR-120: Adopting the Experiment 35 Winning Setup as the App Default

- **Date:** 2026-11-25
- **Status:** Proposed. The rules in this record are accepted at the Experiment 35 freeze (gate G7,
  as for ADR-119). This record holds no adopted values: a separate, later ADR names them and cites
  `<out>/selection.json`. The SHA-256 of this file goes into the OSF deposit with the freeze.
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Amends:** [ADR-018](018-balanced-retrieval-defaults.md), where the adoption changes the chunk
  overlap (100 tokens) or the reranker default. [ADR-019](019-reranker-disabled-for-technical-workloads.md)
  turned the global reranker off; the `documents` profile keeps ADR-018's reranker-on intent.
- **Related:** [ADR-063](063-model-token-aware-markdown-chunking.md),
  [ADR-065](065-ocr-fallback-gate-promoted-to-packaged-default.md),
  [ADR-084](084-context-windows-and-an-owned-llama-server.md),
  [ADR-106](106-app-searches-and-downloads-local-models.md),
  [ADR-119](119-experiment-35-model-matrix-and-claim-checker.md),
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

This record fixes the rules now, so the choice cannot follow the results. Section numbers below
refer to `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md`.

1. **Only levels of the four tested factors can be adopted.** These are embedder size
   (Qwen3-Embedding 0.6B, 4B or 8B), chunk size (512, 1,024 or 2,048 Qwen3 tokens, with the overlap
   at 15 % of the chunk size), reranker (off, or Qwen3-Reranker 0.6B, 4B or 8B) and hybrid search
   (on or off). The experiment held every other value fixed: temperature, seed, reasoning, context
   budget, answer rounds, metadata extraction, OCR and the output cap. This record adopts none of
   them. Each one needs its own ADR. The experiment ran with OCR off and a sent output cap, so its
   results say nothing about the app's OCR default or an app-side cap.
2. **The winner.** The winning setup is the A3 cell in `<out>/selection.json` (section 14.1), with
   the `configuration_hash` time-stamped under section 14.2 step 4. Adoption waits for half-B
   scoring and for gates G1 to G3 (section 15) to pass.
3. **Cost rule (owner decision 2026-11-25).** The experiment gives the evidence; the adoption weighs
   cost. The rule follows the one-standard-error rule practice (Hastie, Tibshirani and Friedman,
   *The Elements of Statistical Learning*, section 7.10).
   1. Take the A3 winner.
   2. The candidate set is every tested setup whose pooled half-B nDCG@10 is within 0.02 of the
      winner's. Pool as in section 14.1, on half B. 0.02 is the pre-registered SESOI (section 10).
   3. Adopt the cheapest candidate that passes the Mac limits. Cost order, cheapest first: smaller
      embedder, then smaller or no reranker, then hybrid off, then larger chunk size (fewer stored
      chunks).
   4. A heavier option is adopted only if it beats every lighter candidate by at least 0.02.

   **Mac limits.** Measure them on the owner's reference Mac (Apple silicon, 64 GB unified memory),
   through the app itself. The p95 search latency over a fixed query sample must be at most 2 s. The
   resident memory of the embedder, reranker and answer model together must be at most 24 GB. Ingest
   time is reported, not gated. The adoption ADR records the measurements.
4. **Where the values go.** Adopted values go into `src/omrs/config/profiles/documents.yaml` only.
   The global default (`Settings` model and `defaults.yaml`) and the `codebase` profile do not
   change. If a factor's half-B estimate for its adopted level is below -0.02 on any core dataset,
   that factor is not adopted and keeps its current value. Such an effect depends on the dataset
   (section 7 calls an opposite-sign result a dataset-dependent effect).

   Today a per-collection profile owns only a few levers, such as `top_k`, `rerank_enabled` and
   `hybrid_enabled` (`src/omrs/core/profiles/resolver.py`). The embedder, chunk size, overlap and
   reranker model and backend come from the server default. So the adoption needs a change that
   lets `documents.yaml` own these keys, or the adoption ADR states the gap.
5. **Comparison with today's app default.** A descriptive, retrieval-only arm that runs the current
   app default on half B is being added to the experiment (owner chose option a; a separate
   amendment designs it). The adoption ADR reports the winner against that arm.
6. **Scope.** The adoption holds within scope S (section 2, the "Scope S" paragraph). Non-English
   collections and the `codebase` profile get no evidence from it.
7. **Hybrid depth.** If a hybrid-on, reranker-off setup is adopted, the app pool rule must change to
   the measured depth (100 per side, fused cut 100) before the default changes, or the adoption ADR
   states that the app result is not the measured one. A hybrid default also needs the `hybrid`
   extra (`rank_bm25`, `nltk`) in the install.
8. **Rollout and re-ingest.**
   - New defaults apply to new collections only.
   - Existing collections keep their stamped settings. The UI shows that a collection was built with
     older defaults.
   - A re-ingest writes a new collection. The app swaps to it only after a check passes, so the old
     index is the rollback. OMRS never mixes old and new chunks in one collection.
   - The release is `feat!`, because existing collections need a re-ingest to get the new defaults.
   - The model download path pins the reranker GGUF SHA-256 ([ADR-106](106-app-searches-and-downloads-local-models.md)).
   - Before the reranker is adopted, the app shows a visible warning when reranking fails and falls
     back to the first order (row 23).
9. **Post-adoption check.** Before the adoption ADR is accepted, run the adopted setup through the
   app's own defaults (CLI or MCP, no pins) on a fixed half-B sample. Its nDCG@10 must match the
   harness within 0.005, the back-end tolerance of section 15. Then run a smoke query on the live
   app. If the check fails, the adoption ADR states the gap, or the default is reverted.
10. **Paper methods and docs.** The paper's methods statements live in one place:
    `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` section 8. When the adoption lands,
    grep `docs/guides/` for the old default values (for example `chunk_overlap` 100, chunk size
    1,024 and the MiniLM reranker) and update each hit.

## Harness against app: every difference

Markings: **Adopt** (the `documents` profile takes the winner's value, under decisions 1 to 4),
**Harness-only** (stays an experiment step), **Paper** (the paper's methods must state it),
**Own ADR** (fixed in the experiment; a change to the app needs its own ADR). A row can carry more
than one. Rows where the harness and the app run the same code with the same value, and the paper
needs no sentence, are left out (profile name, embedding batch, exact vector search, RRF constant
60, score threshold 0.0, rerank decision, client timeout and retries, concurrency, query cache,
citation parse, evidence order). File and line evidence is in the audit.

| # | Step | Experiment 35 harness | App default | Marking |
| --- | --- | --- | --- | --- |
| 1 | OCR during ingest (item 1) | Off, pinned and checked (fixed 2026-11-25, A6) | On: page OCR fallback, local `pp-ocrv6-small`, OCR worker for escalated pages | Harness-only; Paper; Own ADR. App default not measured |
| 2 | Answer output cap (item 2) | `max_tokens` 2,048 sent; finish reason per reply recorded (fixed 2026-11-25, A7) | 2,048 sizes the prompt only; no cap sent | Harness-only; Paper; Own ADR |
| 3 | Hybrid depth and cut (item 3) | 100 dense plus 100 BM25, fused cut 100, then first 10 | Reranker off: 10 per side, fused cut 10 | Adopt (pool rule) only if hybrid-on, reranker-off is adopted (decision 7); else Paper and the gap is stated |
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
| 14 | Chunk overlap | 15 % of the chunk size (77, 154, 307) | 100 tokens at any size | Adopt with the chunk size, at 15 % of it |
| 15 | Token counter | Qwen3-Embedding-4B tokenizer `5cf2132a`; run refuses the legacy fallback | Same tokenizer; falls back to the legacy splitter with a warning | Adopt (tokenizer cached at install); Paper. Before adoption, confirm the tokenizer hash is identical across the three Qwen3 embedders |
| 16 | Metadata extraction | Off | LLM title, keywords and summary, embedded | Paper; Own ADR. App default not measured |
| 17 | Embedded text | Chunk text plus `file_name` and `header_path` | Same rule | Paper (FinanceBench names hold company and year) |
| 18 | Embedder | Qwen3-Embedding 0.6B, 4B or 8B, Q8_0, SHA-256 pinned | Qwen3-Embedding-4B Q8_0 | Adopt (winner, file SHA-256); re-ingest rule applies |
| 19 | Embedder server preset | No `embd-normalize`, `parallel`, `kv-unified` | Adds `embd-normalize 2`, `parallel 1`, `kv-unified false` | Adopt the shipped preset if the check passes: max cosine distance at most 1e-6 on 20 chunks. If it fails, the app takes the harness preset (pre-freeze task 16.36) |
| 20 | Query instruction | Empty | Empty | Paper |
| 21 | Search depth | `top_k` 100, `fetch_k` 100, unassembled; first 10 used | `top_k` 10 | Harness-only (`fetch_k`, `unassembled` exist only on the Python Engine); Paper |
| 22 | BM25 | `rank_bm25` 0.2.2, Porter stems, k1 1.5, b 0.75 | Same code; needs the `hybrid` extra | Adopt the extra in the install if hybrid is adopted |
| 23 | Reranker | Qwen3-Reranker 0.6B, 4B or 8B on llama.cpp; a failed rerank stops the stage | ONNX MiniLM cross-encoder; a failed rerank falls back to the first order with no visible sign | Adopt (backend, size, SHA-256) only after the app shows a visible warning on a failed rerank (decision 8); Paper. Fallback path not measured |
| 24 | Reranker instruction | Fixed llama.cpp Qwen3 template, recorded | OMRS sends no instruction | Paper |
| 25 | Context assembly | Private `assemble` on the kept head, no neighbour expansion | Same call inside `search()` | Harness-only |
| 26 | Evidence selection | 10 chunks, or a 20,480-token cut for `-t20k` setups | `top_k` chunks only | Harness-only. A token budget is a separate proposal |
| 27 | Answer entry | `Engine.answer(rows=...)` | `Engine.answer` runs its own search | Harness-only |
| 28 | Answer prompt | `GROUND_TEXT_QA_TEMPLATE`, one round, no refine | Same template, refine on later rounds | Paper |
| 29 | Answer model and host | `deepseek/deepseek-v4.1-flash-1017`, `deepinfra/fp8`, no fallback | llama.cpp, no model until the user picks one | Paper; Own ADR. The default model is a separate choice |
| 30 | Temperature and seed | 0 and seed 20261101 | Not sent (LlamaIndex 0.1, no seed) | Paper; Own ADR |
| 31 | Reasoning | `none` | Host default | Paper; Own ADR |
| 32 | Context budget and rounds | 131,072 characters, one round | 8,192 characters, four rounds | Paper; Own ADR. A 131,072-character budget can overflow the context window of a local llama.cpp model (default 16,384 tokens, ADR-084) |
| 33 | Rate limits and resends | Gate with waits, resend on `--resume`, third error closes as missing | One call | Harness-only; Paper (missing counts) |
| 34 | Claim checking | Separate stage, GLM-5.3 and Clef-Flash, own settings | Inline, off by default | Harness-only; Paper |
| 35 | Closed-book run | Own prompt through private `prepare_models` | No such mode | Harness-only |
| 36 | Oracle run | Gold pages through the private PDF reader | No such mode | Harness-only |
| 37 | Evidence measurement | Private fit and measure functions; metadata block not counted | Same functions in the answer path | Harness-only; Paper (which characters are counted) |
| 38 | Ragas, claim kinds, length check, determinism, refusals, RAGFlow | Experiment tools | None | Harness-only |
| 39 | FreshStack query text | Title, blank line, body | What the user types | Paper |
| 40 | Workspace profiles | Config and state folders moved; workspace not moved | Read-only catalogue | Harness-only |

## Consequences

### Positive

- Each difference between the measured setup and the app has a written fate before the results
  exist, so the adoption cannot pick its rules after seeing the scores.
- The cost rule keeps a heavier model out of the default when its gain is below the SESOI, and the
  Mac limits keep the default usable on the owner's reference machine.
- The paper's methods list has one copy (protocol section 8), so the paper and the app default
  describe the same pipeline.
- The two unintended differences (OCR on, no output cap) were fixed before any main-run data.
- A re-ingest goes into a new collection, so the old index stays as the rollback.

### Negative

- The adopted setup can score up to 0.02 nDCG@10 below the A3 winner on half B.
- Some measured settings cannot reach the app by a settings change alone: the hybrid depth rule, the
  20,480-token evidence cut, the fenced code export, and the profile keys of decision 4. Adopting a
  setup that depends on them needs code changes or a stated gap.
- The app keeps several values the experiment did not measure (OCR on, metadata extraction on, the
  four-round refine path, no output cap). The app result can differ from the paper's numbers.
- A new embedder or chunk size means a full re-ingest of every live collection that should use it,
  and a `feat!` release.

### Neutral

- The prompt metadata block (path, name, score) is the same in the app and the experiment; any
  change is a separate proposal with its own evaluation.
- The global default and the `codebase` profile stay as they are.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **Adopt the whole harness configuration as the app default** | Several harness steps (fenced export, token cut, depth 100, sealed indexes, resend gate) are measurement tools, not app behaviour. Some have no app equivalent. |
| **Adopt the A3 winner as it is, with no cost rule** | A heavier embedder or reranker costs memory and latency on every query. A gain below the SESOI does not pay for that on a Mac. |
| **Change the global default as well** | No benchmark measured code folders as the app chunks them, and scope S covers English text only. |
| **Change the app to match the harness before the run** (OCR, output cap, hybrid depth) | Changes product behaviour with no measurement of the app side. The experiment pins its own values; the app follows only measured winners. |
| **Decide the adopted defaults after seeing the results, with no rules now** | The choice could then follow the scores. Fixing the rules and the markings before the freeze keeps the adoption honest. |
| **Do nothing; keep app defaults** | The benchmark result would then describe a pipeline nobody runs. |

## References

- Audit: DATA `experiments/35-full-rag-benchmark-2026-11-01/harness-vs-app-audit-2026-11-25.md`
- `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` sections 2 (scope S), 7
  (dataset-dependent effects), 10 (SESOI), 14.1 and 14.2 (selection and time-stamp), 15 (gates and
  back-end tolerance)
- `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` section 7 (notes of 2026-11-25) and
  section 8 (methods statements)
- `experiments/35-full-rag-benchmark-2026-11-01/plan.json` amendments A6 and A7, `pins.settings`,
  `pins.recorded.hybrid`
- `experiments/35-full-rag-benchmark-2026-11-01/arms.py` (`settings_values`),
  `answers35.py` (`cap_answer_output`), `live35.py` (`LiveDeps.engine`)
- `src/omrs/core/retrieval/policy.py` (pool rule), `src/omrs/core/answer/evidence.py` (prompt
  metadata), `src/omrs/core/answer/synthesis.py` (prompt budget),
  `src/omrs/core/profiles/resolver.py` (profile-owned levers)
- Hastie, T., Tibshirani, R. and Friedman, J. (2009). *The Elements of Statistical Learning*, 2nd
  edition, section 7.10 (the one-standard-error rule).
- [ADR-018](018-balanced-retrieval-defaults.md), [ADR-019](019-reranker-disabled-for-technical-workloads.md),
  [ADR-084](084-context-windows-and-an-owned-llama-server.md),
  [ADR-106](106-app-searches-and-downloads-local-models.md),
  [ADR-119](119-experiment-35-model-matrix-and-claim-checker.md)
