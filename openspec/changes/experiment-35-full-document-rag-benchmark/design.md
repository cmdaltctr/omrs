# Design: Experiment 35 Reproducible Local RAG Benchmark

## Status

DRAFT. Measured execution must not begin until the protocol and plan are committed (Confirmatory) and the pipeline sweep has passed.

Source of the agreed decisions: `docs/proposals/first-publication-benchmark.md` (Draft 1, 27 October 2026). Where that document and an earlier version of this change disagree, that document wins. From A4, `preregistration.md` wins on every design fact; the proposal stays the master plan for scope, order of work and Part 2.

**Pre-freeze amendment A4 (2026-11-14, D0.15): `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` governs the live design of Experiment 35.** Where it and this design differ, it wins. D0 to D0.14 and D1 to D10 are history wherever they differ from it. Text that A4 changes carries the marker "(superseded by A4, D0.15)".

**Pre-freeze amendments A3 (D0.14), A2c (D0.13) and A2 (D0.12), all 2026-11-13, win over A1 where they differ; A3 wins over A2c on the selection rule, and A2c wins over A2. Pre-freeze amendment A1 (2026-11-12) wins over every older section.** Section D0 below holds the full-factorial redesign agreed with the operator on 2026-11-12. Sections D1 to D10 keep the earlier plan for history. Where they disagree with D0, D0 wins. No measured run had started when A1 was written: only smoke runs, which are never scored.

## D0. Pre-freeze amendment A1: full-factorial redesign (2026-11-12)

### D0.1 What changed and why

The six one-factor arms (`documents-profile-4b`, `embedding-0.6b`, `embedding-8b`, `reranker-off`, `chunking-off`, `hybrid`) answer one question each against one baseline. They cannot show whether two choices interact, for example whether a bigger embedder gains more from bigger chunks. A1 replaces them with a full factorial of four factors on the search stage, and a smaller full cross on the answer stage.

Other changes in A1:

- Setups are named by their settings, never by a profile name. A search setup name is `e<embedder>-c<chunk size>-r<reranker>-h<hybrid>`, for example `e4b-c1024-r0.6b-hon`. An index name is `e<embedder>-c<chunk size>`.
- Legal RAG Bench joins as a fourth dataset. FreshStack uses its 203 public queries.
- MiniLM (`cross-encoder/ms-marco-MiniLM-L-6-v2`) leaves the experiment, because it truncates every pair at 512 tokens. That hides the effect of 1,024- and 2,048-token chunks. The reranker factor is now off or Qwen3-Reranker 0.6B, 4B or 8B.
- The `chunking-off` arm is dropped. Every setup uses model-token-aware chunking with the pinned Qwen3 tokenizer (ADR-063).
- Granite Guardian is dropped completely, and so is the secondary hypothesis H-CC. The refusal rule stays, no longer tied to H-CC.
- The $250 cap is replaced by a re-estimated budget and a stop rule at a stated ceiling (D0.9).
- Isnad is out of scope (it moved to v4).

### D0.2 Datasets (English only)

Every dataset has gold passages (or gold documents or pages) and human reference answers.

| Dataset | Questions | Corpus | Gold unit | Reference answers | Licence | Status |
|---|---:|---|---|---|---|---|
| FinanceBench open sample (`PatronusAI/financebench`) | 150 | 84 PDFs, 12,013 pages | Document and page | Yes, plus a number-match check | CC BY-NC 4.0 | Confirmatory |
| FreshStack LangChain (`freshstack/queries-oct-2024`, `freshstack/corpus-oct-2024`) | 203 | Full public LangChain corpus, 49,514 documents (A4, D0.15) | Documents | Nuggets, usable for context recall | CC BY-SA 4.0 | Confirmatory |
| BioASQ mini (`enelpol/rag-mini-bioasq`, test split) | 707 | 40,181 PubMed passages | Passages | Yes | CC BY 2.5 | Confirmatory |
| Legal RAG Bench (`isaacus/legal-rag-bench`) | 100 | 4,876 passages (Victorian Criminal Charge Book) | One passage per question | Yes, written by experts | CC BY-NC-SA 4.0 | Exploratory (low power) |

Total: 1,160 questions.

Notes:

- The HF id `PatronusAI/financebench` was checked on 2026-11-12 (150 rows, `evidence_page_num` per evidence item). The plan already used it.
- FreshStack: the earlier plan counted 223 queries. That number held 20 continuity queries from Experiment 9, which are not part of the public benchmark. A1 uses the 203 FreshStack queries only. The 15 continuity documents and the overlay runbook served only the continuity queries, so they leave the corpus (operator decision, 2026-11-13). (Superseded by A4, D0.15: all 9 FreshStack indexes use the full public corpus of 49,514 documents at a pinned revision; the subset below is retired.) The corpus was the public LangChain slice: 10,009 manifest rows, about 9,994 unique files after the 2 repeated upstream ids are counted once. The harness drops its overlay references (`datasets35.py` `_FS_OVERLAY`, `_FS_OVERLAY_ID` and the `continuity/` glob), and a new corpus tree hash is recorded at the freeze.
- Legal RAG Bench: `qa` config (100 rows: `id`, `question`, `answer`, `relevant_passage_id`) and `corpus` config (4,876 rows: `id`, `title`, `text`, `footnotes`), both split `test`. Checked on 2026-11-12. With 100 questions and one gold passage each, the minimum detectable effect is about 5 nDCG points. Its results are labelled exploratory in every table. CC BY-NC-SA: never released under CC BY, derived files under CC BY-NC-SA.
- LegalBench-RAG and LLeQA are out.
- FinanceBench answers also get a number-match check: the numbers in the reference answer must appear in the generated answer after unit normalisation (D0.6).

### D0.3 Search-stage factors (full factorial, all four datasets)

| Factor | Levels |
|---|---|
| Embedder | Qwen3-Embedding 0.6B, 4B, 8B (Q8_0 GGUF, llama.cpp b11941) |
| Chunk size | 512, 1,024 and 2,048 Qwen3 tokens. Overlap 15% of the size: 77, 154 and 307 |
| Reranker | Off, or Qwen3-Reranker 0.6B, 4B, 8B |
| Hybrid | Off (dense only), or on (BM25 plus dense, RRF), with `retrieval.hybrid_sparse_backend: bm25` pinned |

That gives 9 indexes per dataset (embedder x chunk size) and 72 search setups (9 x 4 x 2). Each search setup runs once on its sealed index (D0.7). Metrics as before: nDCG@10 (primary endpoint), Recall@10, MRR@10, and hit@page for FinanceBench. Scoring counts documents, pages or passages, never chunks.

Fixed in every setup: `top_k` 10; reranker candidate pool `max(rerank_max_fetch, top_k x rerank_fetch_multiplier)` = 100 (OMRS defaults); `similarity_threshold` 0.0 (default, so no reranker score drops a result); metadata extraction `disabled`; tokenizer `Qwen/Qwen3-Embedding-4B` at revision `5cf2132a`; the reranker instruction is the default one that llama-server applies (D0.10).

**One chunk size per level for every file type.** OMRS uses `chunking.markdown_chunk_size` for Markdown text and `chunking.chunk_size` for plain text (`src/omrs/core/ingestion/chunker.py:229`). Markdown text is a `.md` file or a reader that declares `text_format` `markdown` (`chunker.py:148-157`). So the harness sets both keys to the level value, and `chunking.chunk_overlap` to 15% of it. How each dataset routes (checked 2026-11-12):

| Dataset | Files | Splitter path | Size key | Token counter |
|---|---|---|---|---|
| FinanceBench | PDF through `pdf_inspector` (the default reader, declares `text_format="markdown"`, `src/omrs/integrations/pdf/registry.py:159-168`) | Markdown, model-token-aware | `markdown_chunk_size` | Qwen3 tokenizer |
| FreshStack | `.md` | Markdown, model-token-aware | `markdown_chunk_size` | Qwen3 tokenizer |
| BioASQ | `<id>.md` (written by `datasets35.py`; was `.txt`) | Markdown, model-token-aware | `markdown_chunk_size` | Qwen3 tokenizer |
| Legal RAG Bench | `<id>.md` (planned) | Markdown, model-token-aware | `markdown_chunk_size` | Qwen3 tokenizer |

Decision (operator, 2026-11-13): BioASQ and Legal passages are written as `.md`, so all four datasets are chunked and counted with the pinned Qwen3 tokenizer through `markdown_chunk_size`. Before this decision, `.txt` passages went through the plain `SentenceSplitter`, which counts tiktoken cl100k tokens (the LlamaIndex default). The passages hold no Markdown headings, so the Markdown path gives one section per passage and splits it by Qwen3 tokens: the only change is the token counter. Risk: a passage line that starts with `#` would read as a heading. The loader escapes a leading `#` on any line, and a test proves that every chunk of all four datasets has at most the level's Qwen3 token count and that no chunk goes through the cl100k counter.

### D0.4 Hypotheses (pre-registered)

(Superseded by A4, D0.15: rows, tests and Holm families are in `preregistration.md` sections 7 to 9. This paragraph and the table are A1 history.) Unit: the question. A factor's marginal score for a question is its mean nDCG@10 over every cell of the other factors at that level. For example, the 4B marginal averages the 24 setups with the 4B embedder. Each contrast is a paired permutation test (10,000 shuffles, seed 20261101) on per-question marginal scores, with a paired 95% bootstrap interval. Holm correction runs across the 11 primary contrasts within one dataset. A contrast counts when the Holm-adjusted p is below 0.05, the interval excludes zero, and the sign matches the stated direction.

| Id | Statement | Contrast(s) |
|---|---|---|
| H1 | A bigger embedder finds better documents | 4B vs 0.6B; 8B vs 4B |
| H2 | The reranker helps | Reranker on (mean of the three sizes) vs off |
| H3 | Hybrid search helps | Hybrid on vs off |
| H4 | Reranker plus hybrid beats either alone (interaction) | Both on vs reranker only; both on vs hybrid only. H4 holds when both contrasts count |
| H5 | A bigger reranker ranks better | 4B vs 0.6B; 8B vs 4B (reranker-on setups only) |
| H6 (superseded by D0.12 and D0.13: confirmatory on FinanceBench and FreshStack only; the short-set clause is withdrawn) | Chunk size changes search quality on long-document sets (FinanceBench, FreshStack), not on short ones (BioASQ median passage about 364 tokens, Legal passages at most 512) | 1,024 vs 512; 2,048 vs 1,024. Holds when at least one contrast counts on each long set, and on each short set both paired intervals lie inside plus or minus the minimum detectable effect |
| H7 | Bigger embedders gain more from bigger chunks (embedder x chunk size interaction) | Per question: (8B at 2,048 minus 8B at 512) vs (0.6B at 2,048 minus 0.6B at 512), paired test of the two differences |

BioASQ and Legal act as a built-in control for H6. Legal results are exploratory (D0.2). Minimum detectable effect, stated before the run with `min_detectable_effect`: about 4 points at 150 and 203 questions, about 2 at 707, about 5 at 100. (Superseded by A4, D0.15: the MDE table comes from the pilot, `preregistration.md` section 10.)

Code: `paired_permutation`, `paired_bootstrap`, `holm`, `wilson` and `min_detectable_effect` from the existing statistics code (`experiments/_lib/stats.py`, `stats_d6.py`). No new statistics code. The marginal averaging is data preparation, not a new statistic. (Superseded by A4, D0.15: the readiness change adds tested statistics code, `stats_cluster.py`.)

### D0.5 Answer stage

**Selection rule (fixed before the run).** After the search stage, choose one embedder size, then one reranker size:

1. Pooled score (amended A3, D0.14: the mean over the three core datasets only, Legal excluded; the earlier four-dataset wording is kept for history): the plain mean of the four per-dataset mean nDCG@10 values, so BioASQ's 707 questions do not dominate. For the embedder, average over every chunk size, reranker level and hybrid level. For the reranker size, use the chosen embedder and average over chunk size and hybrid, reranker-on setups only.
2. Pick the smallest size whose pooled score is within 0.01 of the best size's pooled score (a gap of exactly 0.01 counts as within).
3. Ties: equal pooled scores pick the smaller size.

The rule runs on saved search scores on the Mac. Its inputs and result go into `protocol.md` as a dated note before the replicate pods start.

**Answer setups.** At the chosen embedder and reranker size: chunk size (3) x reranker on or off x hybrid on or off = 12 setups. Each runs 3 times on 1,160 questions: 41,760 answers. (Amended by A2 and A3: 15 setups.)

Fixed: answer model `deepseek/deepseek-v4.1-flash-1017` (OpenRouter, one pinned host, temperature 0, seed 20261101); Ragas 0.4.3 judge `openai/gpt-oss-120b`; claim checkers GLM-5.3 (main, Z.AI Coding Plan endpoint as in `arms.py`) and Clef-Flash (second, local). No cross-check judge: `openai/gpt-6.1-terra` is removed, because no cost estimate included it (A4, D0.15).

**Refusal rule (kept, no longer tied to H-CC).** `openai/gpt-oss-120b` sorts each claim as fact, refusal or mixed. Primary faithfulness uses factual claims (fact and mixed). Refusals are reported apart. The classifier gate stays: agreement of at least 0.90 and refusal recall of at least 0.90 on 100 operator-labelled claims, seed 20261112. The GLM-5.3 against Clef-Flash kappa report stays.

**Answer-stage hypothesis H8.** (Superseded by A4, D0.15: H8 splits into H8a and H8b, Legal RAG Bench is exploratory, and the Holm families are fixed in `preregistration.md` section 8.) Chunk size changes faithfulness and correctness. Expected direction: faithfulness falls as chunks grow. Wang et al. (EMNLP 2024) report faithfulness 97.6 at 512, 94.3 at 1,024 and 80.4 at 2,048 tokens. Contrasts per dataset: 1,024 vs 512 and 2,048 vs 1,024, marginal over reranker and hybrid, with the 3 runs averaged per question first. Outcomes: GLM-5.3 faithfulness on factual claims; Ragas answer correctness on all four datasets; FinanceBench number match. Holm across the H8 contrasts within one dataset.

**Answer correctness on all four datasets (operator decision, 2026-11-13).** The Ragas stage adds a fifth metric: `AnswerCorrectness` from `ragas.metrics.collections`, Ragas 0.4.3 (the version the harness pins), called as `ascore(user_input, response, reference)` with each dataset's human reference answer. It uses the frozen Ragas judge `openai/gpt-oss-120b` and the local 4B embedder for its similarity part, with the library's default weights (factual 0.75, semantic similarity 0.25), recorded in the protocol. References: FinanceBench `answer`, FreshStack reference answer, BioASQ `answer`, Legal RAG Bench `answer`. The FinanceBench number match stays as a second, deterministic check.

**Correctness validation before the metric counts.** (Superseded by A2 M4 and A4, D0.15: 200 main-run answers, 50 per dataset, and a gate per core dataset on the kappa point estimate and lower bound.) The operator hand-labels a stratified, seeded sample of 100 answers (seed 20261113): 25 per dataset, spread evenly over the three chunk sizes, blind to the Ragas score, as correct or not correct against the reference. The Ragas score is made binary at a threshold fixed before labelling (0.5). The report gives Cohen's kappa between judge and operator, per dataset and pooled. Rule fixed before labelling: with pooled kappa of at least 0.60, answer correctness is a reported H8 outcome; below 0.60, it is reported as exploratory only and H8 rests on faithfulness and the FinanceBench number match. Labelling uses answers from the pre-freeze test pod session, not from the scored run.

**Answer context budget: one round (operator decision, 2026-11-13).** At 2,048 tokens and `top_k` 10, the evidence is about 20,000 Qwen3 tokens, at most about 92,000 characters (10 chunks of up to about 9,200 characters). OMRS packs evidence into at most `answer.max_rounds` rounds of `answer.context_window` characters, minus 2,048 reserved for the reply and 1,536 for the template (`src/omrs/core/answer/synthesis.py:169-189`). A1 sets `answer.context_window` to **131,072 characters** and `answer.max_rounds` to **1** in every answer setup. The round budget is then 127,488 characters, enough for every setup's evidence in one completion call, with no refine round. The prompt is then about 35,000 tokens at most. A pre-freeze task reads the context length of `deepseek/deepseek-v4.1-flash-1017` from the OpenRouter models API on the pinned host and records it; the freeze is blocked unless it is at least 65,536 tokens (prompt plus the 2,048-token reply, with margin). A test fails if any answer setup's largest evidence set needs more than one round. The harness still records per answer the rounds, the evidence characters and any `[evidence truncated]` marker; truncation is data, never silent.

### D0.6 FinanceBench number match

A tested function extracts the numbers from the reference answer and from the generated answer. It normalises thousands, millions and billions, currency signs, percent signs and parentheses for negatives. A question passes when every reference number appears in the answer, equal after rounding to the reference's decimal places, or within 1% relative difference. It is a secondary, deterministic correctness check. It needs no judge.

### D0.7 Runs, determinism and rebuild

- The search stage runs once per setup (run 1; operator decision, 2026-11-13). Rationale: query-time retrieval on a fixed, sealed index is deterministic. The FreshStack smoke rerun (ADR-119, `fs-rerun/`) retrieved the same ranked lists as the first run, and G1 checks this again for the 15 answer setups across three pods. Index-time determinism, the part that can vary (embedding batches, GPU kernels), is covered by the G2 rebuild check. Three search runs of 72 setups would add about 194 pod hours and nothing to the statistics, because the search scores have no run-to-run variance to average.
- G1 (determinism): each replicate pod's answer stage retrieves again for its run. For the 15 answer setups (A3), runs 1, 2 and 3 must retrieve exactly what the search stage retrieved. A mismatch is a finding and is reported. It never swaps in another run.
- G2 (rebuild): on the build pod, the `e4b-c1024` index of each dataset is built a second time in a fresh process and searched with `e4b-c1024-roff-hoff`. The ranked lists must match the shared index.
- G3 (preflight): `verify_llamacpp_runtime` passes before the first score, now also for the three reranker GGUF files.

### D0.8 Chunk-size evidence

- NVIDIA chunking benchmark (2025, blog post, not peer-reviewed): FinanceBench scored best at 1,024 tokens with 15% overlap. A1 copies the 15% overlap.
- Jimeno Yepes et al. (2024, arXiv 2402.05131): on FinanceBench, 512 was the best of 128, 256 and 512 tokens.
- Bhat et al. (2025, arXiv 2505.21700): long-context embedders favour chunks of 512 to 1,024 tokens.
- Wang et al. (EMNLP 2024, doi 10.18653/v1/2024.emnlp-main.981): faithfulness falls from 97.6 at 512 to 80.4 at 2,048.
- Tokenizer note: the Qwen3 and cl100k counts agree within 2% on prose, code and BioASQ. On FinanceBench pages Qwen3 gives 1.21 times as many tokens, because it splits digits. So 1,024 Qwen3 tokens is about 850 cl100k tokens on a 10-K page.

### D0.9 Budget and stop rule

(Superseded by A3 and A4, D0.15: estimate about $730, ceiling $975, results-blind drop order.) The $250 cap is gone. The operator has about £2,000 to £3,000. The estimate (method in the readiness change, design D23, on an RTX 4090 at $0.89 per hour) is about **$650** (final figures after A2c, D0.13): about $354 for about 382 pod hours and the network volume, and about $298 for hosted calls (answers about $155 incl. the token-matched and closed-book runs, Ragas about $122 with answer correctness, claim classifier about $11; GLM-5.3 on the Z.AI Coding Plan has no per-token cost). **Ceiling: $975 (1.5 x the estimate).** The largest unknown is reranker speed (llama.cpp issue #30422): at 3 times slower than assumed the total is about $870; at 6 times slower it passes the ceiling and the stop rule triggers before the freeze.

### D0.9a GPU choice and parallel index builds (operator instruction, 2026-11-12)

- **GPU choice.** Before the freeze, the same fixed job of about 10 minutes runs on an RTX 4090 (24 GB), an L40S (48 GB) and an H100 (80 GB): embed 2,000 fixed FinanceBench and FreshStack chunks at 1,024 and 2,048 Qwen3 tokens with Qwen3-Embedding-8B Q8_0, and rerank a fixed set of query-passage pairs with Qwen3-Reranker-8B Q8_0. Each run records chunks per second, pairs per second, peak VRAM, whether the 8B embedder and the 8B reranker load together without swapping, the llama.cpp build, the driver and the image digest. The live price and stock are re-checked before each pod, and the operator gives the go.
- **Decision rule, written into `protocol.md` before the first measurement.** Among the GPUs that hold the 8B embedder and the 8B reranker together without swapping, choose the lowest projected total GPU cost for the main build and search work (9 index builds per dataset plus 72 search setups). When two GPUs are within 10% on cost, choose the faster one. The protocol records the measurements, prices and choice.
- **One GPU type.** Every main-run pod (index build pods, search and replicate pods) uses that one GPU type, and every stage runs on it. GPU types are never mixed. The earlier 4090 pre-freeze runs were preparation, not results.
- **Parallel builds.** The 9 indexes are independent. They build on 9 parallel pods of the chosen GPU type, each into its own store on the RunPod network volume; each pod seals its index and runs its 8 search setups. On a 4090 this takes about 18 h of wall time instead of about 133 h on one pod, for about the same pod hours. The three replicate pods start after the selection rule. End to end, about 4 days of pod wall time. Spending is checked at three points: before the freeze (test pod extrapolation), on the build pod after the search stage (before the replicate pods), and while the replicate pods run (pod billing plus provider spend). When the projected total reaches the ceiling, the results-blind drop order of `preregistration.md` section 17 applies (A4, D0.15); no operator choice decides what is dropped. The OpenRouter key gets a credit limit equal to the hosted share of the ceiling, so an overrun ends as a clean `out_of_credit` stop.

### D0.10 Fact checks (2026-11-12)

1. **Qwen3-Reranker under llama.cpp.** Supported through `--reranking` (embeddings with pooling `rank`) and `/v1/rerank`. Support came in ggml-org/llama.cpp PR #15824, merged on 25 September 2025 in release b6578, so b11941 has it. llama-server applies the Qwen3 prompt itself: the converter stores a `rerank` chat template in the GGUF, and the server fills in the query and document with the model card's default instruction ("Given a web search query, retrieve relevant passages that answer the query"). A custom instruction needs a GGUF metadata edit, so A1 keeps the default in every setup. Only GGUFs converted by llama.cpp's own `convert_hf_to_gguf.py` after PR #15824 carry the classifier head. Older or third-party conversions fail to load or give near-zero scores (issues #13820, #16407). Open issue #30422 reports rerank mode about 6 times slower than expected (scores correct). Qwen publishes no official GGUF. Files: `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF` (maintainer-confirmed). For 4B and 8B ggml-org publishes none; `Voodisss/Qwen3-Reranker-{4B,8B}-GGUF-llama_cpp` and `gorse-io/Qwen3-Reranker-{4B,8B}-GGUF` have Q8_0 files converted with the official script but are not maintainer-checked. Model card scores (MTEB-R): 0.6B 65.80, 4B 69.76, 8B 69.02. The test pod checks each file (a relevant pair near 1, an irrelevant pair near 0, and the same ranking as the transformers recipe on a small sample) before its hash is pinned. Fallback if a file fails: the existing `reranker_torch` backend with a sequence-classification conversion of the model, or a new transformers backend using the model card recipe (yes/no logits after an instruction prompt). Cost of the fallback: the `torch` extra on the pod, about 16 GB of VRAM for 8B in bf16 (which cannot share a 24 GB card with the 8B embedder), and a model outside the llama.cpp runtime pin, recorded in the runtime manifest instead.
2. **New reranker backend in OMRS.** One new file `src/omrs/core/retrieval/reranker_llamacpp.py`, one `register("reranker_llamacpp", ...)` line, one entry in the backend map, and `llamacpp` added to the accepted values of `retrieval.rerank_backend`. Built and tested in change `exp35-main-run-readiness` (design D27, task group 12).
3. **FinanceBench text format.** `pdf_inspector` declares `text_format="markdown"`, so FinanceBench uses `markdown_chunk_size` and the Qwen3 tokenizer. BioASQ `.txt` used `chunk_size` and cl100k; from 2026-11-13 BioASQ and Legal are written as `.md` (D0.3). The harness passes settings through the scratch `omrs.jsonc` that `arms.settings_values` writes, and `router_env.check_resolved` refuses an environment or `.env` override. So the harness must write `chunking.chunk_size`, `chunking.markdown_chunk_size` and `chunking.chunk_overlap` into that file for every setup (D0.3).

### D0.11 Questions for A1 and their answers

Decided by the operator on 2026-11-13:

1. FreshStack corpus: the 15 continuity documents and the overlay runbook leave the corpus (D0.2).
2. BioASQ and Legal passages: written as `.md`, so all four datasets count Qwen3 tokens (D0.3).
3. Answer correctness: Ragas `AnswerCorrectness` on all four datasets, validated against 100 operator labels, plus the FinanceBench number match (D0.5).
4. Answer rounds: one round, `answer.context_window` 131,072 characters, `answer.max_rounds` 1 (D0.5).
5. Search runs: once per setup; G1 and G2 cover determinism (D0.7).

Still open: the 4B and 8B reranker repositories, decided by the test pod check.

### D0.12 Pre-freeze amendment A2: methods review (2026-11-13)

An independent methods review ran on 2026-11-13. The operator approved every fix. **A2 wins over D0.1 to D0.11 where they differ.** The operator confirmed that a second labeller exists and that the operator will label about 400 items.

**B1. Scoring by unit, after collapse (blocker).** Today `scoring35.py:39-51` cuts the top 10 chunks and then maps each chunk to its unit. A 2,048-token chunk covers more pages and documents than a 512-token chunk, so bigger chunks raise nDCG@10 by construction. New rule:

1. Retrieve 100 chunks for every setup. Reranker-on setups already score a pool of 100 (`policy.py:63-67`); the reranker returns the full order of the pool, not the top 10. Dense and hybrid setups fetch 100.
2. Map each chunk to its unit: FreshStack document, BioASQ passage, Legal passage, FinanceBench page (`doc#page`).
3. Keep the first occurrence of each unit, in rank order.
4. Cut at 10 units. nDCG@10, Recall@10, MRR@10 and hit@page are computed on these 10 units. A list with fewer than 10 distinct units is scored as it is (missing ranks count as misses).

FinanceBench page credit: (for `evidence_recall_20k`, superseded by A4, D0.15: any-page credit is primary there and first-page credit is a sensitivity; nDCG@10 keeps first-page credit) a chunk counts for its **first page** (the lowest page label it carries). Reason: the rule is fixed per chunk and does not depend on the gold label. The current code gives a spanning chunk the gold page when any page matches (`scoring35.py:49-50`), which favours big chunks again. The token-share rule needs per-page token offsets that the reader does not store. Every chunk's other pages are recorded, and a sensitivity table reports hit@page with "any page" credit.

**Token-matched control.** Equal evidence text: 512 tokens x 40 chunks, 1,024 x 20 and 2,048 x 10 (about 20,480 tokens each). Search stage: a secondary metric, evidence recall at 20,480 tokens (the share of gold units present in the first N chunks, N = 20,480 / chunk size), from the same depth-100 lists, so no extra retrieval. Answer stage: two extra setups (D0.12 M5).

**B2. H6 confirmatory on long-document sets only (blocker).** (Rows, endpoints and the holds rule: `preregistration.md` section 7, A4, D0.15.) H6 is now: chunk size changes unit-level nDCG@10 on FinanceBench and FreshStack. It holds when at least one chunk-size contrast counts on both datasets. BioASQ results on chunk size are a reported sanity check, not evidence. Legal RAG Bench is exploratory throughout and is removed from every confirmatory hypothesis.

**M1. Minimum detectable effect from data.** (Superseded by A4, D0.15: a retrieval-only pilot on 40 seeded half-A questions per core dataset fills the MDE table; SESOI 0.02 nDCG@10 waits for the operator.) Before the freeze, compute the standard deviation of per-question paired differences per dataset and per contrast, from Experiment 22 (FreshStack, per-query nDCG@10) and the pre-freeze smoke and test-pod data (all four datasets). Compute the MDE with `min_detectable_effect` at the Holm-adjusted alpha of the worst rank (0.05 / the number of contrasts per dataset), power 0.80. Separate power checks: the H7 interaction (difference of differences) and any equivalence claim (TOST). After B2 no equivalence claim remains in a confirmatory hypothesis, so TOST power is computed only if one is added. The numbers and their sources go into `protocol.md` before the freeze. The earlier MDE figures (about 4, 2 and 5 points) were guesses and are withdrawn.

**M2. One mixed model per dataset, then planned contrasts.** (Superseded by A2c and A4, D0.15: no mixed model; per-question contrast scores with GEE or the FinanceBench document-level sign-flip test; Holm families fixed at 19, 19 and 8 after the second round.) Per dataset, one linear mixed model: `ndcg10 ~ C(embedder) * C(chunk) * C(reranker) * C(hybrid)` with a random intercept per question, fitted with `statsmodels` `MixedLM` (REML), the version pinned in `uv.lock` (a PEP 735 dependency group `stats` in `[dependency-groups]` of `pyproject.toml`, the same mechanism as the `ragas` group; never an extra and never in the app install; `dev` includes it with `{include-group = "stats"}` so the fast suite runs its tests (decided by the operator, 2026-11-13)). The planned contrasts of H1 to H7 are estimated from the model as follow-ups. Holm runs across every H1 to H8 contrast of one dataset. The paired permutation test and paired bootstrap stay as a robustness check. FinanceBench bootstraps resample whole documents (`paired_bootstrap(groups=doc_name)`, `experiments/_lib/stats_d6.py:140-160`). Cross-dataset rule: a hypothesis holds overall when it is supported on at least 2 of the 3 confirmatory datasets (FinanceBench, FreshStack, BioASQ); H6 needs both long-document sets. Legal is exploratory and never counts.

**M3. Split-half selection.** (Amended by A4, D0.15: FinanceBench is split by document; the others by question.) Each dataset's questions are split into halves A and B with seed 20261115 (stratified by dataset). The embedder and reranker size for the answer stage are chosen on half A only, with the D0.5 rule. All answer-stage headline results are reported on half B. The answer stage still runs on all questions; half A results are secondary. Search-stage hypotheses use all questions.

**M4. Human validation.** (Superseded by A4, D0.15: L1 labels 750 items, L2 225; gates and samples in `preregistration.md` section 11.) Two labellers, recorded as L1 (the operator) and L2 (the second labeller). No names in public records.

| Set | Size (L1) | Drawn from | Stratified by | L2 share |
|---|---:|---|---|---:|
| Claim kinds (refusal gate) | 100 | smoke claims, seed 20261112 | dataset | 30 |
| Faithfulness verdicts | 200 | main-run claims, seed 20261116 | dataset and chunk size | 60 |
| Answer correctness | 100 | main-run answers (half B), seed 20261113 | dataset (25 each) | 30 |
| **Total** | **400** | | | **120** |

Reports: Cohen's kappa of GLM-5.3 and of Clef-Flash against L1 on faithfulness, with bootstrap 95% intervals; correctness kappa per dataset with intervals (the 0.60 rule of D0.5 now applies to the main-run sample); L1 against L2 kappa per set. Disagreement rule, written before labelling: L1 and L2 discuss each disagreement and agree one label; if they cannot agree, the item is labelled "can't tell", left out of the kappa against the judge, and counted. Labellers never see judge scores or verdicts.

**M5. Answer stage: chunk size is confounded with context length.** Chunk-size effects in the answer stage are reported as "chunk size / context length". Two token-matched answer setups join the 12: 512 x 40 and 1,024 x 20 chunks, at the chosen reranker size, reranker on and hybrid on (fixed now, not chosen from data). They are compared with `c2048` x 10 at the same reranker and hybrid levels (amended by A3, D0.14: the comparison uses a separate `c2048-t20k` setup). Total: 14 answer setups (15 after A3). GLM-5.3 against Clef-Flash agreement is reported per chunk size.

**M6. Contamination check.** (Amended by A4, D0.15: a second closed-book run uses the RAG prompt with empty evidence; rows 14, 15, 18 and 19 are re-run on questions both closed-book runs answer wrongly.) One closed-book run (no retrieval, same answer model and settings, one run) on all 1,160 questions, scored with `AnswerCorrectness` and the FinanceBench number match. The report splits RAG answer correctness by retrieval hit versus miss (gold unit in the evidence or not), beside the closed-book correctness.

**M7. Provenance of hosted calls.** Every hosted call (answers, Ragas, GLM-5.3, classifier) records the model id and provider that the reply returns, beside the requested ones. A difference is reported. Raw verdicts (GLM-5.3, Clef-Flash, classifier, Ragas) are released where the dataset licence allows. The local Clef-Flash rerun is named as the path a reader can reproduce without a hosted model.

**M8. Reranker pins and a rank check.** Every reranker GGUF is pinned in the `plan.json` runtime block with its SHA-256 before the freeze. On the test pod, each size is checked against the model card's transformers recipe on 200 seeded query-passage pairs (seed 20261117): Spearman rank correlation of the scores at least 0.95. A file below the threshold is not pinned.

**M9. Public pre-registration.** (Amended by A4, D0.15: `preregistration.md` is the main file of the OSF deposit.) At the freeze commit (G7), the operator deposits `protocol.md` and `plan.json` on OSF as a public pre-registration. The deposit carries no personal data beyond the operator name already allowed in records.

**Answer model (decided by the operator, 2026-11-13).** The answer model stays `deepseek/deepseek-v4.1-flash-1017` on the OpenRouter API. Reason: the open-weights DeepSeek V4.1 Flash has 552B parameters, about 508 GB at 8-bit, which no single pod can host; smaller open models answer worse; the API costs about $127 for all answers. A single answer model is a stated limitation. Oracle retrieval was not added at this point; the operator approved an oracle run later the same day (see the oracle paragraph and D0.13).

**Decided by the operator (2026-11-13), no longer open:** `statsmodels` as the `stats` dependency group; FinanceBench page credit by the chunk's first page, "any page" as a sensitivity column; the token-matched answer setups fixed at reranker on and hybrid on.

**Oracle run (approved by the operator, 2026-11-13).** One oracle answer run (run 1 only) on all 1,160 questions: the answer model `deepseek/deepseek-v4.1-flash-1017` with the same prompt and settings as the main answer setups, and the gold units given directly as evidence, with no retrieval. Sources: Legal RAG Bench, the gold passage; FinanceBench, the gold evidence page text(s) from the PDF as read by `pdf_inspector`; BioASQ, the gold passages (the corpus abstracts named by the question's relevant passage ids), because these are the units retrieval is scored on and they come from the same text the index holds, while snippets are fragments that a real retriever never returns; FreshStack, the gold documents, capped at the token budget of the largest main answer setup (about 20,480 Qwen3 tokens), with any truncation recorded per question as data. It is scored with the same Ragas `AnswerCorrectness`, GLM-5.3 and Clef-Flash claim checks and FinanceBench number match. Reported beside the closed-book run as floor (closed-book) and ceiling (oracle), descriptive only, no hypothesis test. Caveat: the oracle evidence has no distractor passages, so it is an upper bound, not a fair comparison with retrieval. Cost: about $8 hosted and about 4 pod hours on replicate pod 1. New estimate about **$650**, ceiling **$975** (1.5 x).

**Minor fixes.**

- Only nDCG@10 is primary. Recall@10, MRR@10, hit@page and every answer metric are secondary (`plan.json` metrics fixed to match).
- The 3 answer runs at temperature 0 with a fixed seed measure hosted-API nondeterminism, not sampling variance. The report says so.
- The 0.045 and 0.055 sensitivity re-test of the 0.05 cut-off is dropped.
- Limitations stated in the protocol: one answer model; English only; the reranker's default instruction ("Given a web search query, retrieve relevant passages that answer the query") is a web-search instruction applied to finance and legal text.

**Re-cost (A2).** Depth 100 adds no rerank work when the harness passes `fetch_k=100` (A2c, N1; without it the pool would be 300). Two token-matched answer setups add about 6,960 answers at 2,048-level context, and the closed-book run adds 1,160 short answers. Superseded by the A2c final figures below. Method: readiness change design D35.

## Context

The first version of this change planned two small local baselines on the operator's Mac: 35A (FinanceBench subset, `documents` profile) and 35B (RepoProbe answers and FreshStack retrieval, `codebase` profile). Larger runs were to move to a later cloud proposal.

Two things changed on 27 October 2026:

- ADR-103 made llama.cpp with a public GGUF file the only local runtime for experiment evidence. It added the `publication` purpose, which must be Confirmatory and must pin its runtime in `plan.json`.
- The first fellowship paper needs a citable benchmark. The carry-forward review (`openspec/changes/archive/2026-10-27-reproducible-experiment-runtime/carry-forward.md`) chose Experiments 2, 3, 10b, 15, 22 and 25 to go forward as arms of one new `publication` experiment, not as single re-runs.

Experiment 35 becomes that experiment.

## Goals

- Measure the full OMRS pipeline on three public datasets from three domains, with gold labels.
- Measure what four pipeline choices change, one at a time, against one baseline.
- Make every number repeatable by another group on another machine: pinned GGUF files, pinned build, stated tolerance.
- Report uncertainty for every number, and paired comparisons for every arm.
- Release what the licences allow, in a form a Software Tool Article can use.

## Non-Goals

- No production default changes from this experiment. A finding that suggests one goes to a separate proposal.
- No framework comparison inside Experiment 35 (LlamaIndex, Haystack, LangChain, RAGFlow or others). Part 2 compares OMRS with RAGFlow on half B, as `docs/proposals/first-publication-benchmark.md` states (amendment A3, D0.14).
- No RepoProbe answer scoring. It moves to a later paper (see "RepoProbe moved out").
- No Ragas, OpenTelemetry or other evaluation tooling in the base runtime dependency path.
- No decision here on local or cloud hardware. The timing in task 1.4 informs it.

## D1. Purpose, size and runtime

- `experiment.json`: `purpose: publication`, `size: Confirmatory`, `category: retrieval`.
- Commit `protocol.md` and `plan.json` before the first measured run. After that, a change goes only into the `amendments` list.
- `plan.json` holds the ADR-103 `runtime` block:
  - `runtime_under_test: false`.
  - `models[]`: one entry per local model (embedding 0.6B, 4B, 8B; answer model; Ragas judge when local). Each entry names `role`, `repository`, `file`, `sha256`, `runtime: llama.cpp`, `build` and `server_args`.
  - `references[]`: each hosted model, with provider and model id.
  - `tolerance[]`: the largest change in each primary metric that still counts as the same result on another back end (Metal, CUDA, CPU).
- Embedding files come from the public `Qwen/Qwen3-Embedding-0.6B-GGUF`, `Qwen/Qwen3-Embedding-4B-GGUF` and `Qwen/Qwen3-Embedding-8B-GGUF` repositories. Use the same quantisation for all three sizes (Q8_0 unless the freeze records a reason for another).
- Before the first score of each run, call `verify_llamacpp_runtime` from `experiments/_lib/llamacpp_runtime.py`. A wrong build or file hash stops the run. Pass `runtime=found.as_run_record()` to `record_run_start`.
- Models llama.cpp cannot run (the ONNX reranker, OCR engines) stay under the existing runtime-manifest record: name, revision and file hash.
- Hosted models appear only as named reference arms.

## D2. Datasets

### FinanceBench (open sample)

- All 150 questions. Ingest the real source PDFs through the full document path: reader, OCR routing, Markdown interface, chunking, embedding, LanceDB.
- A run that starts from pre-extracted text does not count as the primary result. It may be reported as a diagnostic.
- Hit rule: a retrieved chunk is a hit when its source is the gold `evidence_doc_name` and its page is the gold page. `evidence_page_num` is zero-indexed. One function converts it to the page numbering that OMRS stores, with a unit test on a known page. A chunk that spans pages is a hit when any of its pages is the gold page. A result row's pages are its `page_labels` (a merged row lists every page it spans, from `add-merged-result-page-labels`), with `page_label` as the fallback for a row without them. A question with several evidence entries is a hit at K when any gold page is hit within the top K.
- Licence CC BY-NC 4.0. Keep the PDFs and derived text out of git and out of any CC BY release.

### FreshStack, LangChain slice (history; superseded by A4, D0.15: full public corpus)

- The slice exported by `prepare_freshstack.py` with seed 20260530: about 10,024 parent documents, all 223 queries, the qrels of Experiments 9a and 22. Indexing is the main cost; a smaller query set only widens the intervals.
- Build a new index for each arm. Experiment 22 does not count as a baseline. It used default chunking (32,631 chunks), `qwen/qwen3-embedding-4b` through OpenRouter, hybrid RRF k=60, rerank off and top_k 50. Report it beside the result as a reference and name the settings that differ. Experiment 9a used one vector per parent document, so its numbers are not comparable.
- Map each retrieved chunk to its parent document and keep only the first rank of each parent before scoring, as Experiment 22's `run_eval.py` does. Reuse that mapping code.
- Licence CC BY-SA 4.0. Release derived files under CC BY-SA.

### BioASQ (`enelpol/rag-mini-bioasq`, test split)

- 707 questions over 40.2K PubMed abstracts, with gold passage IDs and reference answers. A hit is a retrieved chunk whose passage ID is a gold passage ID.
- Licence CC BY 2.5.
- The test split has no question-type field (columns: `question`, `answer`, `id`, `relevant_passage_ids`; checked 27 October 2026). The 40.2K-abstract corpus is the cost, and the question count does not change it. So a smaller question set does not save index time. If indexing does not fit the time budget, run BioASQ on rented hardware (open question 2), or shrink the corpus to every gold passage plus a seeded random sample of the rest. A shrunk corpus makes retrieval easier, so the report must state it and its size.
- Before freeze, check that every `relevant_passage_ids` value exists in the corpus. Report the count of missing IDs, and drop a question only when none of its gold passages exists.
- The licence on the Hugging Face card is CC BY 2.5. The abstracts come from PubMed, and BioASQ's own terms need registration. Publish IDs and scores only.
- Fallback: NFCorpus (`BeIR/nfcorpus`), retrieval scores only, no Ragas. Use it only when BioASQ cannot be used. Check its academic-use terms first.

### RepoProbe moved out

RepoProbe (old 35B-1) moves to a later paper. It labels no gold files or chunks, so it gives no retrieval metric, and every score needs a hosted LLM judge. The scoring notes decided on 2026-10-23 stay valid for that later paper: call `SimpleScorer.score_answer_multiple` directly at a pinned RepoProbe commit; judge `glm-5.3` through Z.AI at `reasoning_effort: low` with `num_iterations=3`; optional 5-question check with a second judge; label the result "single-shot RAG on RepoProbe" and never compare it with the agent scores in the RepoProbe paper.

## D3. Arms

All arms run on the same questions. Each ablation changes one component against the baseline.

| Arm | What changes | Past evidence it carries forward |
|---|---|---|
| Baseline | `documents` profile defaults, Qwen3-Embedding-4B (local GGUF) | Experiment 3 (end-to-end); Experiment 22 used 4B through OpenRouter |
| Embedding 0.6B | 0.6B in place of 4B | Experiments 2 and 22 |
| Embedding 8B | 8B in place of 4B | Experiment 2 (0.6B and 8B tied on an easy 17-query set) |
| Reranker off | Reranker off against the baseline's on | Experiments 10b and 15 (the reranker hurt technical retrieval) |
| Token-aware chunking off | Model-token Markdown chunking (ADR-063) off against on | Experiment 25 |
| Hybrid search | Hybrid (BM25 and dense, RRF fusion) in place of dense, reranker on as in the baseline. Reuses the baseline index, so no new embedding | Experiment 22 (hybrid raised FreshStack Recall@5 from 22.7% to 25.6%) |

Notes:

- The `documents` profile is the baseline on all three datasets, FreshStack included. The earlier plan used the `codebase` profile for FreshStack. The proposal replaces that.
- The 8B arm runs on all three datasets, so the three sizes are compared on equal terms. The paper claims only what this arm shows.
- The `documents` profile sets `rerank_enabled: true`, so the reranker arm turns it off.
- Token-aware chunking is on when `EMBEDDING__TOKENIZER_MODEL` and its revision resolve (ADR-063). The off arm leaves them unset, so the legacy Markdown path runs. Before freeze, check which documents of each dataset route through the Markdown splitter. If the arm changes no chunk on a dataset, record the cell as "not applicable" and do not run it. BioASQ abstracts are short and may be such a case.
- Each arm uses the arm's own embedding model for the tokenizer. The Qwen3 embedding family shares one tokenizer.
- Answers come from one pinned answer model for all arms: `deepseek/deepseek-v4.1-flash-1017` through OpenRouter, a named hosted reference (ADR-103), temperature 0, seed 20261101, one upstream host that honours `seed` (operator, 2026-11-08; replaces the 2026-10-27 choice of local Qwen3-4B). The answer model is the same in every arm, so it is not a variable of the comparison. The freeze names the pinned host.
- A judge never scores answers from its own model family. Answers are DeepSeek. The Ragas judges (D4) are OpenAI models and the claim checkers (D4) are GLM, IBM Granite and Clef-Flash, so the rule holds. The earlier fallback judge `google/gemini-3.8-flash` is not needed and is dropped.

## D4. Metrics

### Primary (gold labels, no judge)

- Recall@10, MRR@10, nDCG@10 (binary relevance from the gold labels).
- Hit@page (FinanceBench only), with the D2 hit rule.
- Primary endpoint for the arm comparisons: nDCG@10. Holm correction applies to it. The other primary metrics are reported with intervals and paired differences, without a Holm claim.

### Secondary (LLM judge)

- Ragas 0.4.3: faithfulness, answer relevancy, context precision, context recall.
- Main Ragas judge (operator, 2026-11-08): `openai/gpt-oss-120b` through OpenRouter, a hosted reference (ADR-103), reasoning `low`, temperature 0, fixed seed, one pinned upstream host that honours `seed`. Different family from the answer model. Evidence: Judge's Verdict (arXiv 2510.09738), kappa 0.756, human-like tier.
- (Removed by A4, D0.15; no cross-check judge runs.) Cross-check judge: `openai/gpt-6.1-terra` through OpenRouter on the 50 hand-checked items. It takes a fixed seed but no temperature setting. It is the same vendor family as the main judge, so it checks run-to-run and model-size effects, not family bias. The hand check is the independent evidence. Report agreement between the main judge, the cross-check judge and the hand check.
- Hand-check agreement measure (fixed before the check): the operator scores each of the 50 items blind to the judge, per metric, as supported or not supported. Agreement is Cohen's kappa between the operator and each judge, with a 95% bootstrap interval over items, after the judge score is cut at 0.5. Fit for use: kappa 0.6 or higher (substantial). Below that, the report keeps the Ragas numbers and states the shortfall.

### Faithfulness claim check (OMRS answer verification)

- Every answer's claims are checked against the retrieved context by the OMRS claim checker. Its score is a secondary faithfulness metric beside Ragas.
- Selection rule (fixed before the main run, operator 2026-11-10): the main claim checker is the candidate with the highest LLM-AggreFact average balanced accuracy on the full test split (29,320 rows, leaderboard rule: balanced accuracy per dataset, then the plain mean). A local checker replaces it only if all three conditions hold: it lands within 2 points of it on both the average and RAGTruth; it judges more rows per second (the 2-point allowance exists only to buy speed and cost); and it passes the own-claims guard (amendment 2026-11-11): on the smoke-run claims (all arms, both runs) its unsupported rate is within 15 points of the main checker's on every dataset, and its Cohen's kappa against the main checker is 0.4 or higher. Granite Guardian is slower (2.3 against about 2.8 rows per second) and fails the guard on FinanceBench: it called 70% of 143 smoke claims unsupported (GLM-5.3: 22%), and 23% of 278 BioASQ claims (GLM-5.3: 10%), kappa 0.40 on these 421 claims. Clef-Flash passes the guard on BioASQ and FinanceBench (FinanceBench 32% against GLM-5.3's 22%, a 10-point gap; BioASQ 12% against 10%, a 2-point gap; kappa 0.56), and fails the 2-point condition. The first FreshStack smoke claims do not count: the smoke pod held no FreshStack documents except the overlay runbook, so every answer was an abstention; `datasets35.py` now stops when a gold document is missing. A FreshStack-only smoke rerun (2026-11-11, 383 claims) replaced them: GLM-5.3 39.4% unsupported, Clef-Flash 34.7% (gap -4.7 points, kappa 0.62), Granite 58.7% (gap +19.3 points, kappa 0.52). Clef-Flash passes the guard on all three datasets; Granite fails it on FinanceBench and FreshStack (ADR-119 amendment A7). The guard limits were set after the smoke data was seen; the main run checks the guard again on all claims (ADR-119).
- Main checker, by that rule: GLM-5.3 through the Z.AI API, strategy `chat`, reasoning `low` set explicitly, temperature 0, seed 20261109: 76.9 average, 85.1 RAGTruth. On the Experiment 20 set of 120 triples, reasoning `low` gave recall 1.0 and false rejection 0.0. The GLM-5.3 figure is our own measurement (outputs published); the report notes that the model may have seen LLM-AggreFact data in training.
- Second checker and fallback (amended 2026-11-11): Clef-Flash 9B Q8_0 (local, strategy `clef_flash`): 67.8 and 71.9 on LLM-AggreFact, far below its published 76.6 and 83.2 (the original weights score the same, so the GGUF is not the cause). It agrees best with GLM-5.3 on our own claims (kappa 0.56, 88% same verdict). If GLM-5.3 calls fail, the run stops and resumes when Z.AI is back; the runner never switches by itself. A failed GLM-5.3 call stops the judge stage before that answer is saved, so `--resume` retries it. If GLM-5.3 is withdrawn for good, the operator names Clef-Flash main in a dated amendment. After all arms and runs have finished, only Clef-Flash rows saved with a call error are judged again (`stages35.judge_stage` saves a failed Clef-Flash or Granite call as a row with an error, and `--resume` skips it). The report gives, per checker, arm and dataset, the count of answers with no verdict because of a call error. H-CC uses only claims that both GLM-5.3 and Granite judged, and is inconclusive when that drops it below 30 questions. Before that, the remaining arms and runs, and the arm that stopped, run with `--judges clef_flash,granite_guardian`, the report lists each arm and run with no GLM-5.3 verdict, and any comparison with GLM-5.3 uses only claims that both checkers judged. The report states the benchmark gap. The FreshStack rerun confirmed this role (kappa 0.62 on 383 claims, ADR-119 amendment A7). It becomes main by the selection rule only after a question fix (74.9 or higher and 83.1 or higher, full split).
- Reported as data (amended 2026-11-11): IBM Granite Guardian 3.3 8B Q8_0 (local, strategy `granite_guardian`): 75.7 and 83.2, which reproduces its published 76.5 and 82.2 within about 1 point. It fails the own-claims guard, so it is never fallback or main in Experiment 35.
- No sampling (operator, firm): all three checkers judge every claim in every arm and every run, so each has equal data. The arm runner runs them per claim (`--judges clef_flash,granite_guardian,chat`). If Granite's speed (2.3 rows per second) strains the budget, add pod time or a second pod at the freeze; never cut coverage.
- Report each checker's faithfulness score per arm, its unsupported rate per dataset, Cohen's kappa of Clef-Flash and of Granite against GLM-5.3 on all claims, and each checker's balanced accuracy beside speed and cost.
- Why 2 points: the claim checker sets the faithfulness scores. Its shortfall against the reference checker must stay well below the minimum detectable effect between arms (about 4 points, D6), or it could hide or invent a difference between arms. 2 points is half the MDE, measured on the full split, where sampling noise is well under 1 point. 1 point was rejected: leaderboard models treated as equivalent already differ by about 1 point (Clef-Flash 76.6, Granite 76.5, gpt-4o 75.9), and the Granite reproduction landed 0.8 below and 1.0 above its published pair. 3 points was rejected: it nears the MDE and spans a full leaderboard tier (gpt-4o 75.9, gpt-4o-mini 74.0). The report calls two checkers "on par" only at a gap of about 1 point or less, as MiniCheck (EMNLP 2024) does. For a gap between 1 and 2 points it writes "slightly lower accuracy" with the numbers, speed and cost.
- Record per call: model ID, upstream provider, temperature, seed, reasoning setting, prompt and completion tokens. Record the Ragas version and the run dates.
- A metric that needs a reference answer runs only where the dataset has one (FinanceBench, BioASQ). Check FreshStack at freeze. Otherwise report "not measured". (Superseded by D0.5 and D0.12: all four datasets carry reference answers. FreshStack's reference is the `answer_text` field of `freshstack/queries-oct-2024`, config `langchain`: the accepted Stack Overflow answer, already loaded by `datasets35.py:172`.)
- Check about 50 judged items by hand. Define the agreement measure in the protocol before the check. Report the agreement.
- Ragas never replaces a primary metric. When a Ragas score improves and a primary metric worsens, report both.

### Latency and diagnostics

- Latency per query: p50 and p95, without warm-up. Measured runs do not run in parallel on one machine.
- Diagnostics: evidence recovery after parsing and OCR, evidence kept after chunking, ingestion time, OCR work and failures, chunk count, embedding tokens, index size.

## D5. Repetitions

- Each arm runs 3 times.
- Each arm builds its index once. Runs 2 and 3 repeat retrieval, answers, the Ragas judge and timing on that index. With a fixed index, runs 2 and 3 must retrieve exactly what run 1 retrieved. This is the determinism check, and the report states its result.
- Rebuild check: for each dataset, rebuild the 4B baseline index once in a fresh process and compare the retrieved lists with run 1. This shows whether index building is repeatable. A full rebuild for every run of every arm would cost many hours and add nothing to the statistics, because retrieval on a fixed index does not vary.
- Embedding mode: exact or fast, as the pipeline sweep's Part C decides. The plan states the mode and its tolerance.
- Run 1 gives the scored retrieval result. A mismatch is a finding: record it, report the run-to-run difference, and do not swap in another run.
- The 3 runs measure the stages that can change: the generated answer, the Ragas judge and latency. The rebuild check covers index building. Report the run-to-run standard deviation for each.
- Tests compare arms question by question. Average the 3 runs for each question first.

## D6. Statistics (basic set; history, superseded by A2c and A4, D0.15: see `preregistration.md` section 9)

For each dataset and arm:

1. Mean with a 95% confidence interval: bootstrap over questions for scores, Wilson for hit rates.
2. Difference from the baseline with a paired 95% confidence interval. This is the main number.
3. One paired test per comparison: permutation test for scores, McNemar's exact test for hit or miss.
4. Holm correction across the arms of one dataset.
5. Wins, losses and ties per question.
6. The minimum detectable effect, stated in the protocol before the run: about 4 points at 150 to 223 questions, about 2 points at 707.

Code: reuse `wilson`, `win_loss`, `mcnemar_exact`, `paired_permutation`, `paired_bootstrap`, `holm` and `min_detectable_effect` from `.agents/skills/s-experiment/references/stats.py`, and `paired_bootstrap_ci` and `cell_record` from `experiments/_lib/stats.py`. If the skill file cannot be imported from the experiment, copy the functions unchanged into `experiments/_lib/stats.py` with their tests. Do not write new statistics code. Add plain nDCG@10 and hit@page to `experiments/_lib/retrieval_metrics.py` without changing the existing definitions.

Hypotheses (one per ablation arm and dataset): H0, the arm's nDCG@10 equals the baseline's. H1, it differs. Decision rule: a difference counts when the Holm-adjusted p is below 0.05 and the paired interval excludes zero. Otherwise report "no difference larger than the minimum detectable effect was found".

One table per dataset:

| Arm | n | Recall@10 [CI] | MRR@10 [CI] | nDCG@10 [CI] | Hit@page % [CI] | Δ nDCG@10 [paired CI] | p (Holm) | W/L/T | Faithfulness ± run SD | Answer relevancy ± SD | Context P / R ± SD | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## D7. Hardware and timing

- Task 1.4 times local 0.6B, 4B and 8B embedding on a fixed slice of each corpus. It records wall time, tokens and peak memory, and extrapolates to each full corpus. The timing is a planning measurement, not a scored run.
- The change `pipeline-sweep-llamacpp` plans the same timing. If its numbers exist for the measurement machine and the pinned files, Experiment 35 reuses them and records the source.
- Fallback: if local 4B does not fit the time budget, the reference arm becomes OpenRouter `qwen/qwen3-embedding-4b`, named as hosted (ADR-103).
- The run may be local (the 64 GB M5 Pro MacBook Pro) or on rented cloud hardware. Rule (decided 2026-10-27): start on the Mac. If the extrapolated embedding time for all arms exceeds about 48 hours on the Mac, embed on a rented GPU; answers and judging stay where they are. Either way: the same GGUF files, the same build, and the D1 tolerance. Run all arms of one dataset on the same machine and back end, so the paired comparisons stay fair.
- Record the hardware (chip or GPU, memory, back end) in every run record.
- Result of task 1.4 (2026-11-10, RTX 4090, llama.cpp b11941, Q8_0): one full index build of all three corpora takes about 2.9 h (0.6B), 3.4 h (4B) and 3.7 h (8B). Per-file parsing and overhead, not embedding, is the largest share (BioASQ about 1.6 h). Protocol section 4.5 holds the rows and the method.
- Machine (task 1.5): the run uses one rented RTX 4090 on RunPod secure cloud (archived change `pre-exp35-harness-and-answer-fixes`, design D9), because the local judges (Granite, Clef-Flash) need the GPU and every arm of one dataset must run on one machine. The Mac was not timed. Price and stock are read again at create time.

## D8. Observability

The harness writes one secret-free JSONL trace per query and major stage, outside the MCP stdout channel. Minimum fields:

- benchmark revision, run ID, arm, repetition number;
- dataset and question ID;
- effective settings and model identities (file hash for local models);
- reader and OCR route where applicable;
- chunk counts;
- retrieved chunk IDs, parent or page IDs and scores;
- reranker input and output ranking where applicable;
- stage durations and token counts where available;
- answer model identity, judge identity;
- error or degraded status.

Failed documents and questions stay in the denominators. The schema stays simple enough to map to OpenTelemetry later. Experiment 35 adds no OpenTelemetry dependency.

## D9. Ragas isolation

Ragas goes in a separate `uv` dependency group (for example `eval`), not in a published extra. The pinned version is 0.4.3 (Apache-2.0). It pulls in `langchain`, `datasets` and `tiktoken`. Before adding it, run a dry resolve and check whether `tests/test_dependency_floors.py` needs an exemption. When Ragas is missing, the primary metrics still run and Ragas metrics are reported as not measured.

## D10. Publication rules that change the experiment

1. A small shareable example set: example input, expected output and a short guide to reading it (Software Tool Article). Use only data whose licence allows sharing, for example a few BioASQ items with attribution.
2. Split `output/` into `output/shareable/` and `output/restricted/`. Restricted holds anything with corpus text or FinanceBench-derived content.
3. Licences: FinanceBench CC BY-NC (never released under CC BY); FreshStack CC BY-SA (derived files under CC BY-SA); BioASQ CC BY 2.5. Publish scores, question IDs and rebuild scripts. Do not publish corpus text.
4. Archive code and shareable outputs on Zenodo with a DOI. Give each dataset's derived files their own archive with their own licence.
5. Before the repository or any release goes public, remove names and home-folder paths, and search the upload for them.
6. `output/` stays out of git. Copy it to `DATA/omrs/experiments/` with SHA-256 checksums before any worktree removal.

## Validity controls

- Freeze dataset revisions, question IDs, gold labels, source file hashes and query order.
- Freeze the FinanceBench page conversion and its test.
- Freeze effective OMRS settings per arm and the `runtime` block.
- Freeze scoring code, metric definitions, the statistics plan and the minimum detectable effect.
- Record the OMRS commit and dependency-lock hashes in each run record.
- Preserve failures in denominators.
- Do not tune on measured outcomes.

## Open questions (resolve at freeze)

1. Resolved 2026-11-08 to 2026-11-10: answer model, Ragas judges and claim checkers (D3, D4).
2. What wall-time, memory and paid-provider budget applies? The local-or-rented rule is in D7.
3. Does BioASQ fit in full, or is a corpus sample needed (D2)?
4. Does FreshStack carry reference answers that Ragas context recall can use? (Answered 2026-11-13: yes, `answer_text`, the accepted Stack Overflow answer; nuggets also exist.)
5. Does the token-aware chunking arm change any chunk on BioASQ?
6. Resolved 2026-10-27: every PDF runs through the production default reader, `pdf_inspector`, with its production fallback chain. No dataset or arm uses a different reader, so the reader is never a hidden variable. The change `pdf-inspector-page-provenance` gives pdf-inspector page numbers and must merge before the pipeline sweep. The run records the reader per file.
7. Resolved 2026-10-27: metadata extraction is `disabled` in every arm. The default `llamaindex` mode calls the language model for every chunk, costs more than it gives here, and its generated text enters the embedded text, so it would add variation between runs. The pipeline sweep still times it, and the report gives that cost.

Resolved on 2026-10-27 by the publication proposal: datasets and sizes, the baseline and arms, metrics, repetitions, statistics, and RepoProbe moved out.

## Risks

| Risk | Response |
|---|---|
| Small differences between llama.cpp back ends | `tolerance[]` per primary metric (ADR-103) |
| The Ragas judge disagrees with people | Report hand-check agreement; Ragas stays secondary |
| Indexing 40K abstracts takes too long | Time first (pipeline sweep Part B); rented hardware, or a stated corpus sample, before scoring |
| The reranker result changes on llama.cpp embeddings | Report it as found; a negative result is still a result |

### D0.13 Pre-freeze amendment A2c: second methods review (2026-11-13)

**Pre-freeze amendment A2c (2026-11-13): second methods review.** It wins over D0.12 where they differ.

- **N1. Rerank pool stays 100.** With `top_k` 100 for depth-100 scoring, OMRS would size the rerank pool as max(`rerank_max_fetch`, `top_k` x `rerank_fetch_multiplier`) = max(100, 300) = 300 (`src/omrs/core/retrieval/policy.py:63-67`, `settings.py:61-62`). The harness passes `fetch_k=100` to `Engine.search` (it reaches the existing `fetch_k_override`, `pipeline.py:279-284`), so every reranker setup scores a pool of exactly 100 and returns all 100 in order. Dense and hybrid setups also fetch 100.
- **N2. Equal evidence by real tokens.** The equal-evidence metric `evidence_recall_20k` and the equal-text answer setups no longer cut by chunk count. They take chunks in rank order and add each chunk's real Qwen3 token count to a running total; a chunk is included when the total before it is below 20,480; the chunk that crosses the limit is truncated at the limit (20,480 is a hard limit, and the truncation is recorded per question), and no later chunk is included. Short documents and short last chunks therefore no longer under-fill the budget. The setup names become `c512-t20k` and `c1024-t20k`; the `c2048` x 10 comparison is cut by the same rule.
- **N3. H6 endpoint on FinanceBench.** First-page credit penalises big chunks. H6 on FinanceBench is tested on `evidence_recall_20k` (gold pages within the 20,480-token evidence), its confirmatory endpoint for H6 (A4, D0.15: with any-page credit; first-page credit is a sensitivity). nDCG@10 with first-page credit and with any-page credit are sensitivity results. H6 counts on FinanceBench only if the 20k measure supports it, and the report gives whether the two page rules agree in sign per contrast. FreshStack keeps unit-level nDCG@10 for H6.
- **N4. p-values from cluster-robust errors.** (Superseded by A4, D0.15: no mixed model; the analysis is `preregistration.md` section 9.) The mixed model with a random intercept per question stays for estimates and description. Each planned contrast's p-value comes from a GEE with the same mean model (`statsmodels` `GEE`, Gaussian, exchangeable working correlation) and cluster-robust standard errors clustered by question; on FinanceBench clustered by document. Holm runs across the contrasts of each dataset. The paired permutation test, or on FinanceBench the document-grouped bootstrap, is the pre-registered sensitivity check.
- **N5. H8 on all questions.** The selection rule averages over chunk size, so choosing on half A barely biases the chunk-size contrasts. H8 is tested on all questions. Descriptive headline answer numbers stay on half B.
- **Minor.** Only nDCG@10 is primary (the tolerance line names the others as secondary; A4, D0.15: nDCG@10 stays the primary metric of the study; `evidence_recall_20k` is the confirmatory endpoint for H6 and H7 on FinanceBench, so `plan.json` flags it `primary` too). FreshStack's reference answer is `answer_text` of `freshstack/queries-oct-2024`, config `langchain` (the accepted Stack Overflow answer). Oracle evidence is capped at 20,480 Qwen3 tokens for every dataset (FinanceBench, BioASQ and FreshStack; a Legal passage is at most 512), with truncation recorded. The one-round test covers the oracle and closed-book stages too. Floor (closed-book) and ceiling (oracle) are single runs, while main setups average 3 runs; the report says so. The report adds a per-question cross-table on retrieval misses: closed-book correct or not against RAG correct or not. Oracle retrieval is now part of the plan (an oracle run, approved 2026-11-13).
- **Cost.** N1 to N5 add no pod hours or calls (the pool stays 100). Final estimate: about **$650** (pods and network volume about $354 for about 382 pod hours, hosted calls about $298), ceiling **$975** (1.5 x).

### D0.14 Pre-freeze amendment A3: selection rule and hand-off to Part 2 (2026-11-13)

Decision (operator, 2026-11-13). The master plan is `docs/proposals/first-publication-benchmark.md`. This section wins over D0.5 and D0.12 where they differ. The full text is `protocol.md` section 0.12.

- **Pooled score.** The embedder and the reranker size are chosen on half A by the mean of the per-dataset mean nDCG@10 over FinanceBench, FreshStack and BioASQ. Legal RAG Bench takes no part. Reason: Legal is exploratory with 100 questions, and a selection input should come from confirmatory sets only.
- **Four-factor pick for Part 2.** At the chosen embedder and reranker size, choose chunk size, reranker on or off and hybrid on or off by the pooled half-A mean nDCG@10 of the 12 cells. Cells within 0.01 of the best tie. Tie order: reranker off, hybrid off, lowest index cost, smaller chunk size. The configuration hash of the chosen cell goes to OSF before half B opens.
- **Hand-off.** Part 2 runs on half B only, once per system. Experiment 35 does not run Part 2, does not run RAGFlow, and does not draw labels from RAGFlow answers. Part 2 has its own protocol (C1, C2, fairness rules, labels).
- **Token-matched control (PR 209 review, 2026-11-13).** The factorial cell `c2048` x 10 keeps its 10-chunk evidence. A separate 15th answer setup, `c2048-t20k`, cuts evidence at 20,480 real Qwen3 tokens at 2,048-token chunks, reranker on and hybrid on, beside `c512-t20k` and `c1024-t20k`. Each chunk size has a token-matched cell, and the token-matched comparison of H8 uses the three `-t20k` setups. Registered before the freeze. It amends D0.13 N2, which cut the `c2048` comparison by the same rule. Cost: the answer stage grows by about 1/14 (about 7%). Counted from the readiness design D35 table (two token-matched setups: +36 pod hours, +$47 hosted), one more setup adds about $24 of hosted calls (answers, five Ragas metrics, judges and classifier) and about 18 pod hours (about $16 at $0.89 per hour, about 6 hours per replicate pod), so about $40 in all. The estimate moves from about $650 to about $690. The ceiling stays $975 (1.5 x the old estimate, 1.4 x the new one). At 3 times slower reranking the total is about $910, still under it.
- **FinanceBench unit in Part 2 (2026-11-13).** Part 2 scores C1 at page level for every FinanceBench question and both systems, the unit used here (first page of a chunk). Pre-freeze gate and document-level fallback are in the master plan, Step 3 rule 3, and protocol section 0.12 item 4.
- **Counts.** The answer stage runs 15 setups (12 crossed plus 3 token-matched), 3 runs each. The 3 runs stay as in D0.12. (Labels superseded by A4, D0.15: 750 L1 and 225 L2.)
- **Framework comparison.** Out of Experiment 35 scope. Part 2 holds it.

### D0.15 Pre-freeze amendment A4: publication review fixes (2026-11-14)

Decision (operator, 2026-11-14). A publication-grade methods review gave 30 findings, F1 to F30. The operator approved every recommended fix. Detail: `protocol.md` section 0.13 and `plan.json` amendment A4.

- **Governing document.** `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` holds the live design of Experiment 35. It wins over this change, `protocol.md` and `plan.json` wherever they differ. It is the main file of the OSF deposit. The proposal stays the master plan for scope, order of work and Part 2. For Part 2 and E1, `preregistration.md` section 18 wins over the proposal on the points it fixes; the frozen Part 2 protocol governs the rest after its freeze.
- **History rule.** D0 to D0.14 and D1 to D10 stay as history. Text that A4 changes carries the marker "(superseded by A4, D0.15)" or "(amended by A4, D0.15)". Unmarked text that disagrees with `preregistration.md` is an error to fix, not a rule.
- **What changes in this change (finding ids from the review):**
  - F1: all 9 FreshStack indexes use the full public LangChain corpus (49,514 documents, pinned revision). The 10,000-document subset is retired. alpha-nDCG@10 is secondary if the nugget labels allow it.
  - F4, F7, F10: no mixed model. Per-question contrast scores. On FreshStack, BioASQ and Legal the decision test is defined by its closed form (mean; Mancl and DeRouen bias-reduced variance; t on n minus 1), with `statsmodels` GEE as the implementation checked against it (`preregistration.md` section 9 point 3); and a document-level sign-flip test on FinanceBench. Holm families fixed at 19 (FinanceBench), 19 (FreshStack) and 8 (BioASQ; second round C3). A gated row stays in its family with p = 1. No equivalence claim, no TOST, no McNemar test as a main test.
  - F5, F22, F23: H8 splits into H8a (crossed setups) and H8b (token-matched setups). Both are confirmatory. Every hypothesis has scope S, numbered rows and a holds rule. H7 is confirmatory on FinanceBench and FreshStack. After the second round (C3, C4), H6, H7, H8a and H8b hold only on FinanceBench and FreshStack, and a two-sided hypothesis needs the same row with the same sign on every dataset its rule needs. Legal RAG Bench is exploratory in every hypothesis.
  - F3, F8, F19: L1 labels 750 items (claim kinds 100, faithfulness 450 from answers to all questions, correctness 200 from half B) and L2 labels 225. Faithfulness gate per checker and correctness gate per core dataset: kappa point estimate at least 0.60 and lower 95% bound at least 0.40. A differential-error rule and a length-controlled check guard H8a and H8b faithfulness.
  - F12: `evidence_recall_20k` gives any-page credit and is the confirmatory endpoint for H6 and H7 on FinanceBench (rows 9 to 11). nDCG@10 stays the primary metric of the study. First-page credit is a sensitivity.
  - F13: a second closed-book run uses the RAG prompt with empty evidence.
  - F14, F21: FinanceBench is split by document. Order: score half A, write `selection.json`, time-stamp the configuration hash on OSF, then score half B. The RQ1 retrieval headline is the A3 cell on half B. "Sealed" applies to indexes only.
  - F15: the token cut truncates the crossing chunk at 20,480 tokens (D0.13 N2 now says so). The `openai/gpt-6.1-terra` cross-check is removed. `plan.json` `frozen` stays empty until the freeze; the pins table (`preregistration.md` section 16) fills it.
  - F17: estimate about $730 plus the pilot (projected from P2), ceiling $975. At the ceiling a results-blind drop order applies: (1) Legal RAG Bench answer generation, (2) the length-controlled check, (3) the closed-book run with the RAG prompt, then stop (second round C6; E1 has its own ceiling). No operator choice.
  - F20: index cost and configuration hash are defined in `preregistration.md` section 14.1.
  - Second round, C1 to C24 (2026-11-14, `protocol.md` section 0.13): the rulings above plus gate intervals by percentile bootstrap, the half-A rule for samples drawn after `halves.json` exists, the seeds table and open item O6 (decided by the owner on 2026-11-14).
- **Out of scope here.** Harness code, scorers and statistics code belong to change `exp35-main-run-readiness`. Part 2 and E1 rules belong to the proposal and change `rag-benchmark-readiness-flow`.
