# Experiment 35: Reproducible local RAG benchmark of OMRS

- **Folder**: `35-full-rag-benchmark-2026-11-01`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: Aizat, with the a-build agent (plan draft; the operator confirms the open values at freeze).
- **Related**: ADR-103 (llama.cpp GGUF runtime), ADR-018 (documents profile), ADR-063 (token-aware chunking), change `experiment-35-full-document-rag-benchmark`, `docs/proposals/first-publication-benchmark.md`. Carries forward Experiments 2, 3, 10b, 15, 22 and 25. Experiment 22 is a reference only, not a baseline.

## 0. Pre-freeze amendment A1: full-factorial redesign (2026-11-12)

Written before the freeze. No measured run had started; only smoke runs, which are never scored. **This section wins over sections 1 to 7 wherever they differ.** Those sections keep the earlier plan for history. Rationale, fact checks and sources: change `experiment-35-full-document-rag-benchmark`, design D0. Implementation: change `exp35-main-run-readiness`.

### 0.1 Question

How do embedder size, chunk size, the reranker and hybrid search, and their interactions, change retrieval quality on four public benchmarks, and how does chunk size change answer faithfulness and correctness at the best-value search settings?

### 0.2 Datasets (English only, 1,160 questions)

| Dataset | Questions | Gold unit | Status |
| --- | ---: | --- | --- |
| FinanceBench open sample (`PatronusAI/financebench`) | 150 | Document and page | Confirmatory |
| FreshStack LangChain slice | 203 (the 20 Experiment 9 continuity queries leave) | Documents; nuggets for context recall | Confirmatory |
| BioASQ mini (`enelpol/rag-mini-bioasq`, test split) | 707 | Passages | Confirmatory |
| Legal RAG Bench (`isaacus/legal-rag-bench`, CC BY-NC-SA 4.0) | 100 (one gold passage each, 4,876 passages) | Passage | Exploratory (low power) |

LegalBench-RAG and LLeQA are out. FinanceBench answers also get a number-match check (0.6).

### 0.3 Search stage: full factorial

| Factor | Levels |
| --- | --- |
| Embedder | Qwen3-Embedding 0.6B, 4B, 8B |
| Chunk size | 512, 1,024, 2,048 tokens; overlap 77, 154, 307 (15%) |
| Reranker | Off, Qwen3-Reranker 0.6B, 4B, 8B (llama.cpp `/v1/rerank`) |
| Hybrid | Off, or BM25 plus dense with RRF (`retrieval.hybrid_sparse_backend: bm25`) |

9 indexes and 72 search setups per dataset, each run once on its sealed index. Setup names come from the settings: `e<embedder>-c<chunk size>-r<reranker>-h<hybrid>`, index names `e<embedder>-c<chunk size>`. MiniLM, the `chunking-off` arm and every profile-named arm are dropped. Every setup sets `chunking.chunk_size` and `chunking.markdown_chunk_size` to the level and `chunking.chunk_overlap` to 15% of it. All four datasets go through the Markdown splitter and count tokens with the pinned Qwen3 tokenizer: FinanceBench (read as Markdown by `pdf_inspector`), FreshStack (`.md`), and BioASQ and Legal passages, written as `.md` (decision 2026-11-13; they hold no headings, so the only change from `.txt` is the token counter). The FreshStack corpus is the public LangChain slice, without the 15 Experiment 9 continuity documents and the overlay runbook (decision 2026-11-13); its new tree hash is recorded at the freeze.

Search runs once per setup (decision 2026-11-13). Query-time retrieval on a sealed index is deterministic (the FreshStack smoke rerun, ADR-119 `fs-rerun/`, matched; G1 checks it again for the answer setups). Index-time determinism is covered by the G2 rebuild check. Fixed: `top_k` 10, reranker candidate pool 100, `similarity_threshold` 0.0, metadata extraction `disabled`, Qwen3 tokenizer revision `5cf2132a`, the default Qwen3-Reranker instruction that llama-server applies.

Metrics: nDCG@10 is the only primary metric; Recall@10, MRR@10 and hit@page (FinanceBench) are secondary. Scoring counts documents, pages or passages, never chunks, after the unit collapse of section 0.10 (A2).

### 0.4 Hypotheses (pre-registered)

Per-question marginal nDCG@10 (mean over every cell of the other factors at that level). Paired permutation test (10,000 shuffles, seed 20261101), paired 95% bootstrap interval, Holm across the 11 primary contrasts of one dataset. A contrast counts when the Holm-adjusted p is below 0.05, the interval excludes zero and the sign matches the direction.

- **H1** A bigger embedder finds better documents: 4B vs 0.6B, 8B vs 4B.
- **H2** The reranker helps: reranker on (mean of three sizes) vs off.
- **H3** Hybrid helps: on vs off.
- **H4** Reranker plus hybrid beats either alone: both vs reranker only, both vs hybrid only. Holds when both count.
- **H5** A bigger reranker ranks better: 4B vs 0.6B, 8B vs 4B (reranker-on setups).
- **H6** (restated by A2, section 0.10, and A2c, section 0.11; the earlier short-set clause is superseded) Chunk size changes unit-level search quality on FinanceBench and FreshStack: 1,024 vs 512, 2,048 vs 1,024. Holds when at least one contrast counts on both. BioASQ chunk-size results are a reported sanity check, not evidence; Legal is exploratory.
- **H7** Bigger embedders gain more from bigger chunks: per question, (8B at 2,048 minus 8B at 512) vs (0.6B at 2,048 minus 0.6B at 512).
- **Null (each)** (amended A3, section 0.12 clarification 1: each null is a zero effect; the sentence below is kept for history): no difference larger than the minimum detectable effect. The earlier guesses (about 4, 2 and 5 points) are withdrawn; the MDE table computed from data is in section 0.10 (A2).
- **Test (A2 wins over the paragraph above).** One linear mixed model per dataset, planned contrasts, Holm across all H1 to H8 contrasts of the dataset, cross-dataset rule 2 of 3 confirmatory datasets. See section 0.10.

### 0.5 Answer stage

- **Selection rule (amended A3, section 0.12: the pool is the three core datasets, Legal excluded; the sentence below is kept for history).** Pooled score = plain mean of the four per-dataset mean nDCG@10 values. Embedder: averaged over all other factors. Reranker size: at the chosen embedder, reranker-on setups, averaged over chunk size and hybrid. Choose the smallest size within 0.01 of the best (a gap of exactly 0.01 counts as within); equal scores go to the smaller size. The inputs and the choice go into a dated note here before the replicate pods start.
- **Setups.** Chunk size (3) x reranker on or off x hybrid on or off = 12 setups x 3 runs x 1,160 questions = 41,760 answers. (A2 and A3 add 3 token-matched setups: 15 setups, 52,200 answers.)
- **Fixed.** Answer model `deepseek/deepseek-v4.1-flash-1017` (OpenRouter, one pinned host, temperature 0, seed 20261101). Ragas 0.4.3, judge `openai/gpt-oss-120b`. Claim checkers GLM-5.3 (main, Z.AI Coding Plan endpoint) and Clef-Flash (second, local). Granite Guardian is dropped, and so is H-CC (section 4.4 keeps its history).
- **Refusal rule.** `openai/gpt-oss-120b` sorts claims as fact, refusal or mixed. Primary faithfulness uses fact and mixed claims; refusals are reported apart. Gate: agreement of at least 0.90 and refusal recall of at least 0.90 on 100 operator-labelled claims, seed 20261112. GLM-5.3 against Clef-Flash kappa is reported.
- **Answer correctness (decision 2026-11-13).** The Ragas stage adds `AnswerCorrectness` (Ragas 0.4.3, `ragas.metrics.collections`, default weights: factual 0.75, similarity 0.25; judge `openai/gpt-oss-120b`, local 4B embedder) against each dataset's reference answer, on all four datasets. Validation before it counts: the operator labels 100 seeded answers (seed 20261113; 25 per dataset, even over chunk sizes; from the test pod session), blind to the score, correct or not. Ragas scores are binarised at 0.5. Pooled Cohen's kappa of at least 0.60: correctness is an H8 outcome. Below 0.60: exploratory only. The FinanceBench number match stays.
- **H8** Chunk size changes faithfulness (GLM-5.3, factual claims) and correctness (Ragas `AnswerCorrectness` on all four datasets; FinanceBench number match). Expected direction: faithfulness falls as chunks grow (Wang et al., EMNLP 2024: 97.6 at 512, 94.3 at 1,024, 80.4 at 2,048). Contrasts per dataset: 1,024 vs 512, 2,048 vs 1,024, marginal over reranker and hybrid, 3 runs averaged per question first, Holm within the dataset.
- **Context budget: one round (decision 2026-11-13).** At 2,048 tokens x `top_k` 10, the evidence is about 20,000 tokens (at most about 92,000 characters). Every answer setup sets `answer.context_window` to 131,072 characters and `answer.max_rounds` to 1: a round budget of 127,488 characters, so every answer is one call with no refine round (prompt about 35,000 tokens at most). The context length of `deepseek/deepseek-v4.1-flash-1017` on the pinned host is read from the OpenRouter models API and recorded here before the freeze; it must be at least 65,536 tokens. A test fails if any setup needs a second round. Every answer row still records its rounds, evidence characters and any truncation. Truncation is data, never silent.

### 0.6 FinanceBench number match

Numbers from the reference answer must appear in the generated answer after unit normalisation (thousands, millions, billions, currency and percent signs, parentheses for negatives), equal after rounding to the reference's decimal places or within 1% relative difference. Secondary correctness outcome, no judge.

### 0.7 Gates

- **G1**: for the answer setups (14 after A2, 15 after A3), the retrieval of runs 1, 2 and 3 equals the search-stage result.
- **G2**: the `e4b-c1024` index of each dataset, rebuilt in a fresh process, retrieves the same ranked lists with `e4b-c1024-roff-hoff`.
- **G3**: `verify_llamacpp_runtime` passes for every pinned GGUF file, the three reranker files included, before the first score.

### 0.8 Budget and stop rule (replaces task 1.11 and the $250 cap)

Estimate about $650 on an RTX 4090 (after A2c; about $690 after A3, section 0.12; pods and network volume about $354 for about 382 pod hours, hosted calls about $298; method in change `exp35-main-run-readiness`, design D23). **Ceiling $975 (1.5 x the estimate)**, pods and hosted calls together. Checked before the freeze (test pod extrapolation), on the build pod after the search stage, and while the replicate pods run. At the ceiling the run stops before the next stage and the operator decides. The OpenRouter key carries a credit limit equal to the hosted share of the ceiling, so an overrun ends as a clean `out_of_credit` stop.

### 0.8a GPU choice and parallel index builds (operator instruction, 2026-11-12)

- **Timing job.** On an RTX 4090 (24 GB), an L40S (48 GB) and an H100 (80 GB), the same fixed job of about 10 minutes: embed 2,000 fixed FinanceBench and FreshStack chunks at 1,024 and 2,048 Qwen3 tokens with Qwen3-Embedding-8B Q8_0, and rerank a fixed set of query-passage pairs with Qwen3-Reranker-8B Q8_0. Record chunks per second, pairs per second, peak VRAM, whether the 8B embedder and the 8B reranker load together without swapping, the llama.cpp build, the driver and the image digest. Re-check the live price and stock before each pod; the operator gives the go.
- **Decision rule (fixed here, before any measurement).** Among the GPUs that hold the 8B embedder and the 8B reranker together without swapping, choose the one with the lowest projected total GPU cost for the main build and search work (9 index builds per dataset plus 72 search setups), from the measured rates and the live hourly price. When two GPUs are within 10% on that cost, choose the faster one. The measurements, the prices with their date and the choice go into a dated note here.
- **One GPU type.** Every main-run pod (index build pods, search and replicate pods) uses the chosen GPU type, and every stage runs on it. GPU types are never mixed. The earlier 4090 pre-freeze runs (smoke runs, LLM-AggreFact runs, timing in section 4.5) were preparation, not results.
- **Parallel index builds.** The 9 indexes build on 9 parallel pods of the chosen GPU type, each into its own store on the RunPod network volume. Each pod seals its index and runs its 8 search setups. The `e4b-c1024` rebuild check runs beside them (amended A3, section 0.12 clarification 2: it runs after that seal and before any search into the shared output folder). Then the Mac scores the search stage and applies the selection rule, and the three replicate pods start.

### 0.9 Questions decided on 2026-11-13

The operator chose: (1) FreshStack corpus without the continuity documents and the overlay runbook; (2) BioASQ and Legal passages as `.md` with Qwen3 counting; (3) Ragas `AnswerCorrectness` on all four datasets with a 100-answer hand-label check, plus the FinanceBench number match; (4) one answer round, `answer.context_window` 131,072 characters; (5) one search run per setup. Still open: the 4B and 8B Qwen3-Reranker GGUF repositories, chosen by the test pod check.

### 0.10 Pre-freeze amendment A2: methods review (2026-11-13)

An independent methods review ran on 2026-11-13; the operator approved every fix. **This section wins over sections 0.3 to 0.9 where they differ.** Detail: change `experiment-35-full-document-rag-benchmark`, design D0.12; code: change `exp35-main-run-readiness`, design D35 and task group 15.

- **Unit scoring.** Every search setup saves the top 100 chunks (the reranker returns its whole 100-candidate pool in order). Chunks map to units (FreshStack document, FinanceBench page, BioASQ or Legal passage); the first occurrence of each unit is kept in rank order; the list is cut at 10 units. A FinanceBench chunk counts for its first page; "any page" credit is a sensitivity column only. Reason: cutting 10 chunks before mapping lets bigger chunks cover more units and raises nDCG@10 by construction.
- **Token-matched control.** (Superseded in part by A2c N2, section 0.11: evidence is cut by the real Qwen3 token total up to 20,480, not by chunk count; the answer setups are `c512-t20k` and `c1024-t20k`, plus `c2048-t20k` added by A3, section 0.12.) Search: evidence recall at 20,480 tokens (first 40, 20 or 10 chunks at 512, 1,024 or 2,048). Answer: two extra setups, 512 x 40 and 1,024 x 20 chunks at the chosen sizes, reranker on and hybrid on, compared with 2,048 x 10 at the same levels. 14 answer setups (15 after A3, section 0.12).
- **Confirmatory sets.** FinanceBench, FreshStack and BioASQ. H6 is confirmatory on FinanceBench and FreshStack only; BioASQ chunk-size results are a sanity check. Legal RAG Bench is exploratory throughout and in no confirmatory hypothesis.
- **Model and tests.** Per dataset, one linear mixed model, `ndcg10 ~ C(embedder) * C(chunk) * C(reranker) * C(hybrid) + (1 | question)`, fitted with `statsmodels` `MixedLM` (REML, version pinned in `uv.lock`; installed from the `stats` dependency group, never in the app install). Planned contrasts for H1 to H7 from the model; Holm across every H1 to H8 contrast of the dataset. Paired permutation and bootstrap stay as robustness checks; FinanceBench bootstraps resample whole documents. A hypothesis holds overall when supported on at least 2 of the 3 confirmatory datasets; H6 needs both long-document sets.
- **Minimum detectable effect.** Before the freeze: the SD of per-question paired differences per dataset and contrast, from Experiment 22 (FreshStack) and the smoke and test-pod rows; MDE at alpha 0.05 / contrasts per dataset, power 0.80; a separate power figure for the H7 interaction. No equivalence claim remains, so no TOST. Table (filled before the freeze):

  | Dataset | Contrast | SD of paired differences | Source | MDE |
  | --- | --- | --- | --- | --- |
  | (to fill, task 4B.2) | | | | |

- **Split halves.** Each dataset's questions are split into halves A and B (seed 20261115). The embedder and reranker size for the answer stage are chosen on half A. Answer-stage headlines are reported on half B. Search hypotheses use all questions.
- **Human validation.** Labellers L1 (operator) and L2 (second labeller); no names in public records. L1 labels 400 items: claim kinds 100 (smoke, seed 20261112), faithfulness verdicts 200 (main run, seed 20261116, stratified by dataset and chunk size), correctness 100 (main run, half B, seed 20261113, 25 per dataset). L2 labels 30% of each set. Reports: kappa of GLM-5.3 and Clef-Flash against L1 with 95% bootstrap intervals; correctness kappa per dataset with intervals (the 0.60 rule of 0.5 applies to this sample); L1 against L2 kappa per set. Disagreement rule: L1 and L2 discuss and agree one label; if they cannot, the item is "can't tell", left out of the judge kappa and counted. Labellers never see scores or verdicts.
- **Answer stage reading.** Chunk-size effects in the answer stage are reported as "chunk size / context length". Checker agreement is reported per chunk size. The 3 runs at temperature 0 with a fixed seed measure hosted-API nondeterminism, not sampling variance.
- **Closed-book run.** One run, all 1,160 questions, no retrieval; correctness reported beside RAG correctness split by retrieval hit or miss.
- **Oracle run (approved by the operator, 2026-11-13).** One oracle answer run (run 1 only) on all 1,160 questions: the answer model `deepseek/deepseek-v4.1-flash-1017` with the same prompt and settings as the main answer setups, and the gold units given directly as evidence, with no retrieval. Sources: Legal RAG Bench, the gold passage; FinanceBench, the gold evidence page text(s) from the PDF as read by `pdf_inspector`; BioASQ, the gold passages (the corpus abstracts named by the question's relevant passage ids), because these are the units retrieval is scored on and they come from the same text the index holds, while snippets are fragments that a real retriever never returns; FreshStack, the gold documents. Every oracle context, on every dataset, is capped at the token budget of the largest main answer setup (20,480 Qwen3 tokens), with any truncation recorded per question as data (A2c). It is scored with the same Ragas `AnswerCorrectness`, GLM-5.3 and Clef-Flash claim checks and FinanceBench number match. Reported beside the closed-book run as floor (closed-book) and ceiling (oracle), descriptive only, no hypothesis test. Caveat: the oracle evidence has no distractor passages, so it is an upper bound, not a fair comparison with retrieval. Cost: about $8 hosted and about 4 pod hours on replicate pod 1. New estimate about **$650**, ceiling **$975** (1.5 x).
- **Provenance.** Every hosted call records the returned model id and provider. Raw verdicts are released where the licence allows. The local Clef-Flash rerun is the reproducible path without a hosted model.
- **Reranker pins.** Every reranker GGUF is pinned with its SHA-256 in `plan.json` after a Spearman check of at least 0.95 against the transformers reference on 200 seeded pairs per size (seed 20261117).
- **Pre-registration.** At the freeze commit the operator deposits this file and `plan.json` on OSF; the link and the commit hash go here.
- **Dropped.** The 0.045 and 0.055 sensitivity re-test of the 0.05 cut-off (section 6).
- **Answer model (decided 2026-11-13).** The answer model stays `deepseek/deepseek-v4.1-flash-1017` on the OpenRouter API. Reason: the open-weights DeepSeek V4.1 Flash has 552B parameters, about 508 GB at 8-bit, which no single pod can host; smaller open models answer worse; the API costs about $127 for all answers. A single answer model is a stated limitation. Oracle retrieval was added later the same day as an oracle run (section 0.10).
- **Limitations.** One answer model; English only; the reranker's default instruction is a web-search instruction applied to finance and legal text.
- **Budget.** Final figures in section 0.11: about $650, ceiling $975 (about $690 after A3, section 0.12).

### 0.11 Pre-freeze amendment A2c: second methods review (2026-11-13)

This section wins over sections 0.3 to 0.10 where they differ. Detail: change design D0.13; code: readiness design D37, tasks 15.2, 15.3, 15.6, 15.12, 15.14 to 15.16.

- **N1. Rerank pool stays 100.** With `top_k` 100 for depth-100 scoring, OMRS would size the rerank pool as max(`rerank_max_fetch`, `top_k` x `rerank_fetch_multiplier`) = max(100, 300) = 300 (`src/omrs/core/retrieval/policy.py:63-67`, `settings.py:61-62`). The harness passes `fetch_k=100` to `Engine.search` (it reaches the existing `fetch_k_override`, `pipeline.py:279-284`), so every reranker setup scores a pool of exactly 100 and returns all 100 in order. Dense and hybrid setups also fetch 100.
- **N2. Equal evidence by real tokens.** The equal-evidence metric `evidence_recall_20k` and the equal-text answer setups no longer cut by chunk count. They take chunks in rank order and add each chunk's real Qwen3 token count to a running total; a chunk is included when the total before it is below 20,480; the chunk that crosses the limit is truncated at the limit (20,480 is a hard limit, and the truncation is recorded per question), and no later chunk is. Short documents and short last chunks therefore no longer under-fill the budget. The setup names become `c512-t20k` and `c1024-t20k`. (Amended by A3, section 0.12: the factorial cell `c2048` x 10 keeps its 10-chunk evidence, and a separate setup `c2048-t20k` takes the token cut.)
- **N3. H6 endpoint on FinanceBench.** First-page credit penalises big chunks. H6 on FinanceBench is tested on `evidence_recall_20k` (gold pages within the 20,480-token evidence), its confirmatory endpoint for H6. nDCG@10 with first-page credit and with any-page credit are sensitivity results. H6 counts on FinanceBench only if the 20k measure supports it, and the report gives whether the two page rules agree in sign per contrast. FreshStack keeps unit-level nDCG@10 for H6.
- **N4. p-values from cluster-robust errors.** The mixed model with a random intercept per question stays for estimates and description. Each planned contrast's p-value comes from a GEE with the same mean model (`statsmodels` `GEE`, Gaussian, exchangeable working correlation) and cluster-robust standard errors clustered by question; on FinanceBench clustered by document. Holm runs across the contrasts of each dataset. The paired permutation test, or on FinanceBench the document-grouped bootstrap, is the pre-registered sensitivity check.
- **N5. H8 on all questions.** The selection rule averages over chunk size, so choosing on half A barely biases the chunk-size contrasts. H8 is tested on all questions. Descriptive headline answer numbers stay on half B.
- **Minor.** Only nDCG@10 is primary (the tolerance line names the others as secondary). FreshStack's reference answer is `answer_text` of `freshstack/queries-oct-2024`, config `langchain` (the accepted Stack Overflow answer). Oracle evidence is capped at 20,480 Qwen3 tokens for every dataset (FinanceBench, BioASQ and FreshStack; a Legal passage is at most 512), with truncation recorded. The one-round test covers the oracle and closed-book stages too. Floor (closed-book) and ceiling (oracle) are single runs, while main setups average 3 runs; the report says so. The report adds a per-question cross-table on retrieval misses: closed-book correct or not against RAG correct or not. Oracle retrieval is now part of the plan (an oracle run, approved 2026-11-13).
- **Cost.** N1 to N5 add no pod hours or calls (the pool stays 100). Estimate after A2c: about **$650** (about $690 after A3, section 0.12) (pods and network volume about $354 for about 382 pod hours, hosted calls about $298), ceiling **$975** (1.5 x).

### 0.12 Pre-freeze amendment A3: selection rule and hand-off to Part 2 (2026-11-13)

Written before the freeze. No measured run has started. The operator approved the decisions below on 2026-11-13. This section wins over sections 0.3 to 0.11 where they differ. The master plan is `docs/proposals/first-publication-benchmark.md`. Where it and this file disagree, the proposal wins.

- **Pooled score (changes the selection rule in section 0.5).** Pooled score = plain mean of the per-dataset mean nDCG@10 over the three core datasets: FinanceBench, FreshStack and BioASQ. Legal RAG Bench takes no part in selection. The rest of the rule in section 0.5 stays: the embedder is averaged over all other factors, the reranker size is chosen at the chosen embedder over reranker-on setups, the margin is 0.01 and equal scores go to the smaller size. Scores come from half A only (section 0.10).
- **Four-factor pick for Part 2.** At the embedder and reranker size chosen above, a second step picks chunk size, reranker on or off and hybrid on or off. The 12 cells are chunk size (3) x reranker (2) x hybrid (2). The score of a cell is its pooled mean nDCG@10 on half A over the three core datasets. The best cell is the cell with the highest score.
- **Tie order.** A cell ties with the best cell when its score is within 0.01 of the best (a gap of exactly 0.01 counts as within). Among tied cells, choose in this order: (1) reranker off, (2) hybrid off, (3) the chunk size with the lowest index cost. If cells still tie, choose the smaller chunk size. Each step applies to the cells left by the step before.
- **Freeze.** The inputs, the chosen cell and its configuration hash go into a dated note in this section. The operator records the hash on OSF before half B is opened for Part 2. The chosen cell is the only OMRS setup in the Part 2 confirmatory comparison.
- **Hand-off of half B.** Experiment 35 reads half B only for answer-stage headline numbers (section 0.10, A2c N5). No selection step reads half B. Part 2 runs on half B, once per system. Half B stays sealed for Part 2 until the hash is on OSF.
- **Labels.** Experiment 35 label counts stay as in section 0.10 (400 items for L1). Part 2 adds its own correctness labels and its own human-agreement sample. These are drawn from answers of both systems, including RAGFlow answers, and run in Part 2. The Part 2 protocol states the counts and the seeds. They do not change the Experiment 35 gates.
- **Hypotheses C1 and C2.** C1 (retrieval) and C2 (answer correctness) belong to the Part 2 protocol. Holm runs per dataset across C1 and C2, then the cross-dataset rule of 2 of 3 core datasets applies. Legal RAG Bench is exploratory. If no correctness measure passes its human-agreement gate (kappa 0.60), C2 is exploratory.
- **Scope.** Comparison with other frameworks is outside Experiment 35. Part 2 compares OMRS with RAGFlow only.
- **Clarifications (PR 209 review, 2026-11-13; items 1, 2 and 4 change no Experiment 35 design, item 3 adds one answer setup).** (1) Each null of H1 to H8 is a zero effect, as A2 dropped equivalence tests: a contrast counts by the decision rule (Holm-adjusted p below 0.05, sign matches). The minimum detectable effect is for power planning and reporting only. This replaces the "Null (each)" line in section 0.4 and the null texts in `plan.json`. (2) G2 order: the `e4b-c1024` rebuild check runs after that index is sealed and before any search writes into the shared output folder. A search stage refuses to start without a passing `rebuild.json` for its dataset, so index pods wait for it. This replaces "runs beside them" in section 0.8a. (3) Token-matched control: the factorial cell `c2048` x 10 keeps its 10-chunk evidence, so the control does not change a factorial cell. A separate 15th answer setup, `c2048-t20k`, cuts the evidence at 20,480 real Qwen3 tokens (the section 0.11 N2 rule) at 2,048-token chunks, at the chosen embedder and reranker size, reranker on and hybrid on. It sits beside `c512-t20k` and `c1024-t20k`, so each chunk size has a token-matched cell, and the token-matched comparison of H8 uses the three `-t20k` setups. The answer stage runs 15 setups (12 crossed plus 3 token-matched), 3 runs each, and G1 covers all 15. The setup is registered before the freeze. Cost: the answer stage grows by about 1/14 (about 7%). Counted from the readiness design D35 table (two token-matched setups: +36 pod hours, +$47 hosted), one more setup adds about $24 of hosted calls (answers, five Ragas metrics, judges and classifier) and about 18 pod hours (about $16 at $0.89 per hour, about 6 hours per replicate pod), so about $40 in all. The estimate moves from about $650 to about $690. The ceiling stays $975 (1.5 x the old estimate, 1.4 x the new one). At 3 times slower reranking the total is about $910, still under it. (4) FinanceBench unit in Part 2 (decided 2026-11-13): Part 2 scores FinanceBench C1 at page level for every question and for both systems, the unit of this protocol (a chunk counts for its first page). Pre-freeze gate: RAGFlow returns a page number for each chunk on a seeded FinanceBench sample. Pre-registered fallback: if the gate fails, the primary unit is the document for every question and both systems. The other unit is a labelled sensitivity analysis. It is required only when both systems provide page provenance; otherwise the report states it is unavailable and gives the count of questions affected. No question is dropped because of a system's output. The master plan, Step 3 rule 3, holds the text.

### 0.13 Pre-freeze amendment A4: publication review fixes (2026-11-14)

Written before the freeze. No measured run has started. A publication-grade methods review (2026-11-13) gave 30 findings, F1 to F30; the operator approved the recommended fix for each on 2026-11-14. **From A4 on, `preregistration.md` in this folder is the governing live design of Experiment 35.** It wins over this file, `plan.json` and the OpenSpec changes wherever they differ. Sections 0.1 to 0.13 and 1 to 7 of this file are history. The proposal stays the master plan for scope, order and Part 2; pre-registration section 18 wins over it on the Part 2 points it fixes, and the frozen Part 2 protocol governs the rest after its freeze. Section 0.9 now sits after 0.8a, so section 0 reads in number order; its text is unchanged.

| Finding | Change | Pre-registration section |
| --- | --- | --- |
| F1 | FreshStack indexes rebuilt on the full 49,514-document public corpus; the 10,000-document subset retired; alpha-nDCG@10 secondary if nugget labels allow | 4, 6, 17, 23 (P1 to P3) |
| F2 | Part 2: reranker shared, RAGFlow cut-off 0 and depth 100, three-column settings table, matched RAGFlow search only if at most $50; the step 7.2a decision fixes the estimand ("selected OMRS against selected RAGFlow" if the search runs, else "against default RAGFlow"); default RAGFlow defined as one run | 18 |
| F3 | Faithfulness gate per checker (kappa at least 0.60, lower bound at least 0.40), 450 claims by chunk size from answers to all questions, differential-error rule, length-controlled check | 11.2 |
| F4 | Numbered contrast table; Holm families fixed at 19 (FinanceBench), 19 (FreshStack), 8 (BioASQ; was 16, changed by C3 below); gated rows stay in with p = 1 | 8 |
| F5 | H8 split into H8a (crossed) and H8b (token-matched), both confirmatory | 7, 8 |
| F6 | Retrieval-only pilot on 40 half-A questions per core dataset; SESOI 0.02 nDCG@10 (open); underpowered rows named | 10 |
| F7 | MixedLM dropped; one clustered method for estimates, intervals and p-values | 9 |
| F8 | Correctness gate per core dataset, 50 items each, point estimate and lower bound; continuous score validated by AUC | 11.2 |
| F9 | Missing-outcome rules per outcome, Part 1 and Part 2 | 12, 18 |
| F10 | Decision test defined by its closed form (Mancl and DeRouen bias-reduced variance, t on n minus 1), `statsmodels` GEE as the checked implementation; FinanceBench document-level sign-flip; C2 fixed as continuous correctness, no McNemar | 9, 18 |
| F11 | Unjudged share at 10 and condensed-list sensitivity; blind audit optional (open) | 21, 11.3 |
| F12 | `evidence_recall_20k` gives any-page credit; first-page credit is sensitivity | 6 |
| F13 | Second closed-book run with the RAG prompt; H8a and H8b correctness re-run on closed-book-wrong questions | 13 |
| F14 | RQ1 headline is the A3 cell on half B; 72-setup table descriptive | 14.3 |
| F15 | One governing file; conflicts settled there (token cut truncates, zero-effect nulls, Legal exploratory in H8a and H8b, `openai/gpt-6.1-terra` cross-check removed, frozen pins) | 1, 3, 7, 8, 11.1, 16 |
| F16 | Existing data declared | 5 |
| F17 | Results-blind drop order at the ceiling: (1) Legal RAG Bench answer generation, (2) the length-controlled check, (3) the closed-book run with the RAG prompt, then stop (E1 left the order, C6 below); "complete with registered drops" defined; "the operator decides" removed; Part 2 budget a pre-freeze task | 17 |
| F18 | Release table per artefact and licence, re-judge kit | 19 |
| F19 | Label guidelines per set, hidden system identity in Part 2, L2 primary in Part 2, conflict of interest; L2 and ethics open | 11.3 |
| F20 | Pins table; index cost and configuration hash defined | 14.1, 16 |
| F21 | FinanceBench split by document; pre-freeze samples from half A; order: score half A, hash, score half B | 4, 14.2 |
| F22 | "Holds" defined per hypothesis; H7 confirmatory on FinanceBench and FreshStack, as H6; H4 named as simple effects | 7 |
| F23 | Every hypothesis scoped (scope S); limitations extended | 2, 22 |
| F24 | nDCG@10, Recall@10 and MRR@10 formulas (trec_eval convention) | 6 |
| F25 | One-build-per-cell assumption stated; optional `e8b-c2048` rebuild | 15 |
| F26 | Checker 2-point tolerance restated against the MDE table | 11.1, 23 (P7) |
| F27 | Expected-maximum estimator for the search-cost figure | 14.3 |
| F28 | Compute table in the report, pre-freeze pods included | 21 |
| F29 | Deviation policy; OSF file upload time-stamps the A3 hash (open) | 20, 14.2 |
| F30 | Reference fixes | 24 |

**Second round (C1 to C24).** A post-fix consistency review (2026-11-14) gave 24 findings, C1 to C24. The orchestrator ruled on each the same day.

| Finding | Change | Pre-registration section |
| --- | --- | --- |
| C1 | OSF category "registration before analysis of the outcome data"; pilot scores on half A are main-run outcome data for the pilot cells | 1 |
| C2 | Pilot: at most the 4 H7 corner indexes per core dataset, not reused; stand-in SD for adjacent levels; cost projected from P2 and approved before the pod; registered fallback without a pilot | 10, 17, 23 (P5) |
| C3 | BioASQ rows 12 to 19 become sanity checks; families 19 / 19 / 8, 46 contrasts; BioASQ MDE alpha 0.05/8; open item O6 | 7, 8, 10, 23 |
| C4 | Two-sided hypotheses hold only when the same row counts with the same sign on every dataset the rule needs (H6, H8a, H8b, C1, C2) | 7, 18 |
| C5 | One gate interval method: percentile bootstrap, 10,000 resamples by question, own seed; differential-error rule on GLM-5.3, either direction | 11.2 |
| C6 | Drop order without E1 (E1 has its own ceiling); contamination check falls back to the own-knowledge run; "complete with registered drops" | 13, 17 |
| C7 | Half-A rule covers samples drawn after `halves.json` exists; earlier samples listed in section 5 | 4 |
| C8 | `statsmodels` pin marked missing: RDY task 15.6 adds the `stats` group | 16 |
| C12 | Search-cost figure: RAGFlow curve only if its matched search runs; "adapted from Dodge et al. 2019", ascending sort | 14.3 |
| C13 | Sign-flip interval assumes a constant additive shift | 9 |
| C14 | Seeds table, one row per seed; new seeds 20261121 to 20261135 wait for P9 | 16, 23 |
| C15 | Task prefixes RDY, C35 and FLOW defined; pointers name the change and task | 1, 16, 18 |
| C16 | P15 is now a check that no file names the cross-check judge | 23 |
| C17 | Clef-Flash gate failure, unclassified claims, correctness sample draw | 11.1, 11.2, 12 |
| C18 | References cited where used; Angelopoulos 2023, Barr 2013 and Kapoor 2024 deleted | 24 |
| C19 | Matched RAGFlow cell list fixed before the FLOW step 7.2 cost measurement | 18 |
| C21 | Where claims and citations come from | 6 |
| C22 | Four fixed search settings added to `plan.json` `decision_rule` | 16 |
| C24 | Why the faithfulness gate is pooled; per-dataset kappa descriptive | 11.2 |

C9, C10, C11, C20 and C23 change only the OpenSpec changes and the proposal (A4 markers, RQ3 wording, OSF deposit list).

**CodeRabbit round 1 (PR 210, 2026-11-14).** Twelve review threads, all fixed before the freeze:

| Change | Pre-registration section |
| --- | --- |
| Primary measure named "faithfulness of cited factual claims", definition unchanged; uncited-segment share as co-outcome; sensitivity with uncited factual segments as unsupported; open item O7; limitation added | 6, 11.1, 21, 22, 23 |
| Undefined gate statistics fail closed (one-class sample fails; undefined resample takes kappa 0 or AUC 0.5, or is left out for the specificity difference; over 5% undefined fails) | 11.2 |
| Early stop only on preflight, G1 to G3 or the ceiling after the last drop step; a failed outcome gate leaves its rows not testable | 17 |
| One same-sign rule: both-datasets rules need both; 2-of-3 rules (C1, C2) need 2 of 3, and an opposite third is reported | 7, 18 |
| Part 2 C2: section 12 rules for both systems, complete pairs, unjudged-as-0 sensitivity | 18 |
| Contamination subset falls back to the own-knowledge run when the RAG-prompt run is dropped | 13 |
| Pilot seed confirmed before the pilot | 23 (P9) |
| OpenSpec only: half-B guard checks the hash of the current selection file; budget check uses 52,200 answers (15 setups x 3 runs x 1,160); pilot-declined path; labelling and closed-book run tasks moved out of the pre-freeze section; Holm family size follows the recorded O6 answer | none |

Cost: estimate about $730 (was about $690) plus the pilot, projected from P2 before the freeze; ceiling $975 unchanged (pre-registration section 17).

## 1. Question

What retrieval and answer quality does the full OMRS pipeline reach on three public benchmarks with pinned local models, and how much do four pipeline choices change it (embedding size, reranker, token-aware chunking, hybrid search)?

The first fellowship paper cites these numbers. The experiment changes no production default; a finding that suggests one goes to a separate proposal.

## 2. Hypothesis

One hypothesis per ablation arm and dataset. The primary endpoint is nDCG@10.

- **H1 (primary, all five ablation arms)**: the arm's nDCG@10 differs from the baseline's on at least one dataset.
- **H0 (null)**: the arm's nDCG@10 equals the baseline's; any observed difference is within the minimum detectable effect.
- **Decision rule**: a difference counts when the Holm-adjusted p (within one dataset, across its arms) is below 0.05 and the paired 95% bootstrap interval on the difference excludes zero. Otherwise the report says "no difference larger than the minimum detectable effect was found".
- **Secondary**: H-CC, the claim checker transfer hypothesis, is in section 4.4. It does not change the arms or the primary endpoint.

## 3. What changes, what is measured, what stays fixed

Six arms run on the same questions. Each ablation changes one component against the baseline.

| Arm | Changes | Carries forward |
| --- | --- | --- |
| Baseline | `documents` profile defaults, Qwen3-Embedding-4B local GGUF | Experiments 3 and 22 |
| Embedding 0.6B | 0.6B in place of 4B | Experiments 2 and 22 |
| Embedding 8B | 8B in place of 4B | Experiment 2 |
| Reranker off | Reranker off against the baseline's on | Experiments 10b and 15 |
| Token-aware chunking off | Legacy Markdown chunking against model-token-aware (ADR-063) | Experiment 25 |
| Hybrid search | Hybrid (BM25 + dense, RRF) in place of dense, reranker on, reuses the baseline index | Experiment 22 |

Fixed in every arm: the datasets and question order, the answer model (`deepseek/deepseek-v4.1-flash-1017` through OpenRouter, temperature 0, seed 20261101, one upstream host pinned at freeze; ADR-119), the Ragas judge (`openai/gpt-oss-120b`, reasoning `low`) and the claim checker (GLM-5.3, section 4.4), metadata extraction `disabled`, 3 repetitions per arm, and one index per arm (the hybrid and reranker arms reuse the baseline index).

Measured: Recall@10, MRR@10, nDCG@10, hit@page (FinanceBench only), Ragas 0.4.3 secondary metrics, latency p50 and p95 per query, and the ingestion diagnostics of design D4.

## 4. Data

| Item | FinanceBench (open sample) | FreshStack (LangChain slice) | BioASQ (`enelpol/rag-mini-bioasq`, test split) |
| --- | --- | --- | --- |
| Questions | 150 | 223 | 707 (or the frozen subset) |
| Corpus | Real 10-K and similar filings, full PDF path | 10,025 parent documents (10,024 from the 9a export plus one overlay file, section 4.1) | 40.2K PubMed abstracts |
| Gold labels | Gold document and gold page (`evidence_page_num`, zero-indexed) | Gold documents | Gold passage IDs and reference answers |
| Unit | Question | Query | Question |
| Licence | CC BY-NC 4.0 | CC BY-SA 4.0 | CC BY 2.5 |
| Already seen | New | Experiments 9a and 22 | New |

- The FreshStack slice is the `prepare_freshstack.py` export, seed 20260530. Task 1.6 records the corpus and qrels hashes.
- Task 1.2 records the FinanceBench revision and the SHA-256 of each PDF. Task 1.7 records the BioASQ revision and hashes. The PDFs and derived text stay out of git and out of any CC BY release.
- Fallback for BioASQ: NFCorpus (`BeIR/nfcorpus`), retrieval scores only. Task 1.8 checks its academic-use terms first.
- A question stays in its denominator even when its pipeline stage fails.

### 4.1 Data provenance (step 6.1, checked 2026-11-09)

All three datasets were already on disk under `~/Development/DATA/omrs/benchmarks/` (FinanceBench, BioASQ) and `~/Development/DATA/omrs/experiments/freshstack-corpus/` (FreshStack). Step 6.1 downloaded nothing. It rechecked hashes, counts and licences. Nothing here goes in git. The worker reports are in `~/Development/DATA/omrs/handoffs/pre-exp35-session/step6.1/`.

| Dataset | Source and revision | Check result |
| --- | --- | --- |
| FinanceBench | HF `PatronusAI/financebench` revision `e04404e3a97f69f79c14d42f24981a1c9c3bcd18`; PDFs from GitHub `patronus-ai/financebench` commit `cc39aeb4afdf33909ee1412188bf89035950c2eb` | 150 questions, 189 evidence items, 84 PDFs (165,527,662 bytes). Every PDF hash matches `PDFS_MANIFEST.json` (SHA-256 `871478cee4d9ee5001b33e4a981015a95c0cca780f5d75051123685886e5c74d`). Every gold `evidence_doc_name` has a PDF, and every PDF is gold for a question. Questions file `financebench_merged.jsonl` SHA-256 `7a1c81789e0fd2f1c37057a7ec0097756d726b05e7228e68e57db8e18c54fd0b`. |
| FreshStack, LangChain slice | HF `freshstack/queries-oct-2024` and `freshstack/corpus-oct-2024`, config `langchain`. The 9a export did not record a revision. The current revisions (queries `023ac3a14caf9d6ebb13d01adcfb8fa05e5a9630`, corpus `069f66dc323e163b48b10d08408d282733d4393b`) date from 2025-04-21, before the export on 2026-05-30, so they are very probably the ones used (an inference). | 223 queries: 203 FreshStack plus 20 continuity queries from Experiment 9. Manifest has 10,024 rows (10,009 FreshStack, 15 continuity); 10,015 unique ids because two upstream ids repeat. 2,237 qrels pairs. Every FreshStack query has gold documents and none is missing. Manifest SHA-256 `f1e97574229ba474e5b77a338eecbb3c756071f630c312757e0d0aebc702e20e`. Experiment 22 `freshstack-qrels.json` SHA-256 `ccd3bc5732d69a3715a322c8557261f4f7c46ca72951ac6dce160e666e4b2c57`; `ground-truth.json` SHA-256 `3860314c74a5c0be4d10f7cdd4d9d55d1daea4cfedf9dcd60d8fbe20d43b4fe8`. Tree hash of `freshstack-corpus/` (10,025 files, sorted `relpath sha256` lines) `62edae1c601b3f11094c7ef0aaf5a4ce1e16bbfbc5c629e617faef462208af2a`. |
| BioASQ | HF `enelpol/rag-mini-bioasq` revision `8a845907dc1cff31d42fa6f7bb9c6eef5f3ae6f6` | All 5 files match `benchmarks/MANIFEST.json`. 707 test questions, none without gold. 6,125 gold references, 6,081 distinct passage ids, all present in the test corpus of 40,181 passages (no duplicate ids or texts, none empty). Use only `text-corpus/test`; the `text-corpus/train` file holds the same rows plus 40 duplicate texts and the dataset card does not declare it. |

**FreshStack overlay (one added document).** Continuity query 009 names `continuity/zzqj-9097-runbook.md` as gold. The 9a export skipped that file because it was untracked in the main checkout, so Experiments 9a and 22 ran with one unanswerable query. Exp 35 adds the file as the 10,025th document from `~/Development/DATA/omrs/benchmarks/freshstack/overlay/zzqj-9097-runbook.md` (SHA-256 `0473106c84f1f7bf1750e6ed03d294cf77c0464347104f64a8b93cf8afa87e0f`, the text holds the gold answer "rotate the amber token"). The existing export is not edited. All 223 queries are then answerable. The 9a and 22 numbers stay as they were and are reference only.

**BioASQ passage length (characters).** Minimum 3, median 1,455, 95th percentile 2,356, maximum 33,420. Estimated tokens (characters divided by 4, an estimate only): median about 364, 95th percentile about 589, maximum about 8,355, total about 14.9 million. The 4B baseline runs with `--ctx-size 8192`, so the longest passages are cut by the embedder; the pod's Part C count (step B) gives the exact figure.

**NFCorpus fallback (task 1.8).** BioASQ passed every check, so the fallback is not used and no NFCorpus terms check was made.

### 4.2 Licences (task 1.3, checked 2026-11-09)

| Dataset | Licence as written | Source checked |
| --- | --- | --- |
| FinanceBench | CC BY-NC 4.0 | HF dataset tag `license:cc-by-nc-4.0`. The GitHub repo has no licence file at the pinned commit (`gh api` licence call returns 404; the tree lists `README.md`, `data`, `pdfs`, `results`, `vectorstores`). Keep PDFs and derived text out of git and out of any CC BY release. |
| FreshStack | CC BY-SA 4.0 for data, Apache-2.0 for code | Both HF dataset cards, and the upstream README at `github.com/fresh-stack/freshstack`. Paper: arXiv:2504.13128. Derived files carry the share-alike term. |
| BioASQ | CC BY 2.5 | HF cards of `enelpol/rag-mini-bioasq` and `rag-datasets/rag-mini-bioasq`, and the BioASQ data page ("The BioASQ data are distributed under CC BY 2.5 license"). The CC BY 2.5 legal code section 3 grants the right to create and distribute derivative works with attribution. The BioASQ page adds that the source data were "accessed courtesy of the U.S. National Library of Medicine" and links the NLM terms. Those terms ask a redistributor to keep the current data or to say clearly that it may not be current. Neither HF card mentions PubMed abstract copyright. This is a record of the text, not legal advice. |

### 4.3 FinanceBench table-text loss (task 1.2a, issue 197)

Method: for each PDF, count pages where table areas hold words (from LiteParse word boxes, OCR off) and fewer than 50 percent of those words reach the reader's page text. Table areas come from a numeric-row heuristic (row tolerance 3.0, cell gap 12.0, at least 3 rows and 10 words per table). Three readers were measured: `pdf-inspector` 1.17.0 (the OMRS default, `pdf_reader` in `src/omrs/config/__init__.py`), LiteParse (what `auto` picks) and `pypdf` 6.16.2. The benchmark uses the default, `pdf-inspector`. A control that assigns each table to the wrong page flagged 3,964 pages, so the measure can detect loss. Script: `~/Development/DATA/omrs/benchmarks/financebench/table_loss.py` (SHA-256 `2e9ac3e45e70314d6cb7fe8b218095bcb763e2c41b8f06507dd741f89e9de175`). Full per-PDF results: `~/Development/DATA/omrs/benchmarks/financebench/table-loss.json` (SHA-256 `eb927523cb7f004183c4cbbe101b7043c04e8db0c41dc23f2f55d30c75f08ccf`).

| Reader | Affected pages | Share of 12,013 pages | Share of 4,328 pages with tables |
| --- | ---: | ---: | ---: |
| `pdf-inspector` (default) | 17 | 0.14% | 0.39% |
| LiteParse | 0 | 0.00% | 0.00% |
| `pypdf` | 15 | 0.12% | 0.35% |

**Decision: no OCR of source pages during corpus prep.** The default reader, `pdf-inspector`, flags 0.14 percent of pages, about 35 times below the 5 percent rule. None of the 168 gold evidence pages is flagged (136 of them hold tables). Most of the 17 flagged pages are false alarms: LiteParse (the word source) attaches footnote markers such as "(d)" to row labels. One real loss: `JPMORGAN_2022_10K` page 2 (table of contents) comes out empty in `pdf-inspector` while `pypdf` reads 5,248 characters. Worst `pdf-inspector` counts: `PFIZER_2021_10K` 3 of 143 pages, `CVSHEALTH_2022_10K` 2 of 213, `JOHNSON_JOHNSON_2023Q2_EARNINGS` 1 of 24.

72 pages (0.60%) have no text layer. Only 3 look like scans (`AMERICANWATERWORKS_2021_10K` pages 151, 153 and 155). The rest look blank. None is a gold page, and none is table loss, so they stay as the reader returns them. The largest counts are `WALMART_2019_10K` 29 of 155 pages, `AMCOR_2020_10K` 10 of 195 and `GENERALMILLS_2022_10K` 8 of 127. Per-PDF counts for the three readers are in `table-loss.json`.

### 4.4 Claim checker and judges (steps 6.2 to 6.5, measured 2026-11-10)

Decision record: ADR-119. Change design D3 and D4.

LLM-AggreFact test split, 29,320 rows (the earlier figure of 29,300 was wrong). Gated, CC BY-ND 4.0: evaluation only, kept out of git, never published in changed form. Scored by the leaderboard rule: balanced accuracy per dataset, then the plain mean. 25 rows are longer than 60,000 characters and overflow the 32,768-token context; they count as wrong and stay in the denominator.

| Checker | Average | RAGTruth | Published pair | Speed | Outputs |
| --- | ---: | ---: | --- | --- | --- |
| GLM-5.3, Z.AI, `chat`, reasoning `low`, temperature 0, seed 20261109 | 76.9 | 85.1 | none | about 2.8 rows/s | `DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/prefreeze-glm/` |
| Granite Guardian 3.3 8B Q8_0, `granite_guardian` | 75.7 | 83.2 | 76.5 / 82.2 | 2.3 rows/s | `.../prefreeze-pod/35-full-rag-benchmark-2026-11-01/output/prefreeze/` |
| Clef-Flash 9B Q8_0, `clef_flash` | 67.8 | 71.9 | 76.6 / 83.2 | 7.5 rows/s | same folder |

Each folder holds a `SHA256SUMS` file. Local models ran on llama.cpp b11941 on one RTX 4090.

- **Reproduction check (each local model within 1 point of its published pair).** Granite: 0.8 below on the average, 1.0009 above on RAGTruth. The script reports "fail" only from that rounding; treated as reproduced. Clef-Flash: 8.8 and 11.3 points below, not reproduced.
- **Selection rule (fixed before the main run).** The main claim checker is the candidate with the highest LLM-AggreFact average balanced accuracy on the full test split, scored by the leaderboard rule. A local checker replaces it only if all three conditions hold: it lands within 2 points of it on both the average and RAGTruth; it judges more rows per second (the 2-point allowance exists only to buy speed and cost); and it passes the own-claims guard (amendment 2026-11-11): on the smoke-run claims (all arms, both runs) its unsupported rate is within 15 points of the main checker's on every dataset, and its Cohen's kappa against the main checker is 0.4 or higher. Today this selects GLM-5.3. Granite Guardian is slower (2.3 against about 2.8 rows per second) and fails the guard on FinanceBench: it called 70% of 143 smoke claims unsupported (GLM-5.3: 22%), and 23% of 278 BioASQ claims (GLM-5.3: 10%), kappa 0.40 on these 421 claims. Clef-Flash passes the guard on BioASQ and FinanceBench (FinanceBench 32% against GLM-5.3's 22%, a 10-point gap; BioASQ 12% against 10%, a 2-point gap; kappa 0.56) but fails the 2-point condition. The first FreshStack smoke claims do not count: the smoke pod held no FreshStack documents except the overlay runbook, so every answer was an abstention; `datasets35.py` now stops when a gold document is missing. A FreshStack-only smoke rerun (2026-11-11, 383 claims) replaced them: GLM-5.3 39.4% unsupported, Clef-Flash 34.7% (gap -4.7 points, kappa 0.62), Granite 58.7% (gap +19.3 points, kappa 0.52). Clef-Flash passes the guard on all three datasets; Granite fails it on FinanceBench and FreshStack (ADR-119 amendment A7). The guard limits were set after the smoke data was seen; the main run checks the guard again on all claims. Its figure is our own measurement (outputs published); it may have seen LLM-AggreFact data in training.
- **Main checker: GLM-5.3.** On the Experiment 20 set of 120 triples, reasoning `low` gave recall 1.0 and false rejection 0.0.
- **Second checker and fallback: Clef-Flash (amended 2026-11-11).** It agrees best with GLM-5.3 on our own claims (kappa 0.56). If GLM-5.3 calls fail, the run stops and resumes with `--resume` when Z.AI is back; the runner never switches checker by itself. A failed GLM-5.3 call stops the judge stage before that answer is saved (`stages35.judge_stage`), so `--resume` retries it. If GLM-5.3 is withdrawn for good, the operator names Clef-Flash main in a dated amendment, and the report states its LLM-AggreFact gap. After all arms and runs have finished, only Clef-Flash rows saved with a call error are judged again (`stages35.judge_stage` saves a failed Clef-Flash or Granite call as a row with an error, and `--resume` skips it). The report gives, per checker, arm and dataset, the count of answers with no verdict because of a call error. H-CC uses only claims that both GLM-5.3 and Granite judged, and is inconclusive when that drops it below 30 questions. Before that, the runner judges the remaining arms and runs, and the arm that stopped, with `--judges clef_flash,granite_guardian`; the report lists each arm and run with no GLM-5.3 verdict, and any comparison with GLM-5.3 uses only claims that both checkers judged. The FreshStack rerun confirmed the Clef-Flash role (kappa 0.62 on 383 claims, ADR-119 amendment A7). The 1,000-row run on the original weights scored the same as our GGUF (70.0 average on both), so the low score is the model on this task, not the conversion. It becomes main by the selection rule only after a question fix (average 74.9 or higher and RAGTruth 83.1 or higher, full split).
- **Reported as data: Granite Guardian (amended 2026-11-11).** It fails the own-claims guard, so it is never fallback or main in this experiment.
- **No sampling.** All three checkers judge every claim in every arm and every run (`run_arms.py --judges clef_flash,granite_guardian,chat`). If Granite's speed strains the budget, the freeze adds pod time or a second pod; coverage is never cut. The report gives each checker's faithfulness per arm, its unsupported rate per dataset, and Cohen's kappa of Clef-Flash and of Granite against GLM-5.3 on all claims.
- **Why 2 points.** The claim checker sets the faithfulness scores. Its shortfall against the reference checker (GLM-5.3) must stay well below the minimum detectable effect between arms (about 4 points), or it could hide or invent a difference between arms. We set the bar at 2 points (half the MDE) on both the average and RAGTruth balanced accuracy, on the full split, where sampling noise is well under 1 point. 1 point was rejected: leaderboard models treated as equivalent already differ by about 1 point (Clef-Flash 76.6, Granite 76.5, gpt-4o 75.9), and our Granite reproduction landed 0.8 below and 1.0 above its published pair. 3 points was rejected: it approaches the MDE and spans a full leaderboard tier (gpt-4o 75.9, gpt-4o-mini 74.0). The report says "on par" only at a gap of about 1 point or less (as MiniCheck, EMNLP 2024); for a gap between 1 and 2 points it says "slightly lower accuracy" with the numbers. It gives every checker's balanced accuracy beside speed and cost: GLM-5.3 76.9 at about 2.8 rows/s, hosted; Granite 75.7 at 2.3 rows/s, local; Clef-Flash 67.8 at 7.5 rows/s, local, about $0.95 of pod time per full split.
- **Secondary hypothesis H-CC (claim checker transfer, registered 2026-11-11, before the freeze).** The pre-freeze smoke run suggested this hypothesis. The main run tests it on new data.
  - **H-CC:** Granite Guardian's unsupported rate exceeds GLM-5.3's by more than 15 points on FreshStack and on FinanceBench. It does not exceed it by more than 15 points on BioASQ.
  - **H-CC0 (null):** the gap is 15 points or less on FreshStack or on FinanceBench, or it is more than 15 points on BioASQ.
  - **Data:** all main-run claims, all arms and all three runs. The 15 smoke questions that suggested H-CC are excluded from the test: BioASQ 4043, 1372, 604, 2291, 1122; FinanceBench `financebench_id_01476`, `_01964`, `_01484`, `_05718`, `_00476`; FreshStack 76404464, 78048414, 77762811, 77828572, 77536364.
  - **Unit:** the question. For each question, compute each checker's unsupported share over all its claims in all arms and runs, then take Granite minus GLM-5.3. Claims from one question are not independent, so the bootstrap draws questions, not claims. A question with no claims in any arm or run (every answer abstained) has no unsupported share. It leaves that dataset's bootstrap, and the report gives the number left out per dataset. If fewer than 30 questions remain for a dataset, H-CC is inconclusive for that dataset and the report says so (rule fixed 2026-11-11, before the main run). If any arm or run has no GLM-5.3 verdict (GLM-5.3 withdrawn before the run finished), the registered all-arms, all-runs population is incomplete: H-CC is inconclusive, and the matched-claims comparison is reported separately as descriptive.
  - **Decision rule:** per dataset, a 95% bootstrap interval on the mean per-question gap (10,000 resamples, seed 20261111). H-CC holds when both of these are true:
    - The lower bound is above 15 points on FreshStack and on FinanceBench.
    - The upper bound is 15 points or less on BioASQ.
    - Otherwise the report says which part failed. No Holm correction: this is one joint hypothesis, separate from H1.
  - **Who is right (descriptive):** draw 100 claims from the main run, with seed 20261111, from claims where Granite and GLM-5.3 disagree. Take both directions, so the operator cannot infer a claim's labels from the selection rule: 25 claims where Granite says unsupported and GLM-5.3 says supported, and 25 where GLM-5.3 says unsupported and Granite says supported, from each of FreshStack and FinanceBench. Take at most one claim from each question across both directions (the claim with the lowest hash of its ID and the seed), so the claims are independent and the Wilson intervals hold. If a group has fewer than 25 questions, take all of them and report the count. Shuffle the 100 claims into one list. Hide the verdicts and the direction. The operator labels each claim against its cited passages. The report gives the share the operator calls supported for each direction, pooled over the two datasets (50 claims each, a 95% interval of about plus or minus 14 points at a 50% share), and for each direction and dataset (25 claims each, wider), with 95% Wilson intervals. A high share in the first direction means Granite over-rejects. A high share in the second direction means GLM-5.3 over-rejects. A low share in the first direction means GLM-5.3 is lenient.
  - **Labelling rules (fixed 2026-11-11, before the main run).** One labeller, the operator. The rules follow the LLM-AggreFact task definition (MiniCheck, Tang, Laban and Durrett 2024, section 2): a claim is supported if and only if the cited passages support it, and each sentence is checked on its own, without the answer around it. The checkers see the same thing: the claim sentence and its cited passages only.
    1. Judge the claim exactly as the checkers see it. Do not fill in a missing subject or a pronoun from the answer or the question. If the claim cannot be checked as written, label it "Can't tell".
    2. Judge the meaning, not the grammar. If a garbled sentence still has one clear meaning and the passages support it, label it "Supported". Label "Can't tell" only when the meaning itself is unclear.
    3. LLM-AggreFact has two labels, supported and unsupported. For the main share, "Can't tell" counts as not supported, so the human label stays on the benchmark's binary scale. The report also gives the "Can't tell" count, and the share with those claims left out.
  - **Practice round (not evidence).** On 2026-11-11 a practice labeller labelled 10 smoke claims (5 FinanceBench, 5 BioASQ) where GLM-5.3 said supported and Granite unsupported: 9 supported, 1 "Can't tell" (a claim with no subject). The round fixed rules 1 and 2. Smoke claims are excluded from H-CC, so these labels are not results.
  - **Reporting:** a secondary finding in the paper, kept apart from H1. Each checker's unsupported rate per dataset, the gap intervals and the hand-label share. The smoke figures (section 4.4 above) are labelled exploratory.
- **Ragas hand check (task 1.10).** The operator scores each of 50 items per metric as supported or not, blind to the judge. Agreement: Cohen's kappa between the operator and each judge, judge score cut at 0.5, with a 95% bootstrap interval over items. Fit for use: kappa 0.6 or higher. Below that, the report keeps the Ragas numbers and states the shortfall.

### 4.5 Embedding timing and machine (tasks 1.4 and 1.5, 2026-11-10)

Machine: RunPod secure cloud RTX 4090 (24 GB), llama.cpp b11941, Q8_0 GGUF files from `plan.json`. Slices: 200 FreshStack files, 200 BioASQ passages, 5 FinanceBench PDFs (568 pages). Sources: 4B rows from this pod session (`prefreeze-pod/48-pipeline-sweep-llamacpp-2026-11-01/output/timing-4b.jsonl`); 0.6B and 8B rows from Experiment 48 on the same machine type, slices and token counts (`DATA/omrs/experiments/48-pipeline-sweep-llamacpp-2026-11-01/output/`). The 4B embedding rate of the two sessions agrees within 4 percent on every slice.

| Model | Corpus | Slice tokens | Embed tokens/s | Peak GPU MB | Full-corpus tokens | Full build (h) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0.6B | FreshStack | 264,317 | 24,741 | 2,617 | 12.0M | 0.77 |
| 0.6B | BioASQ | 50,784 | 12,384 | 2,617 | 14.4M | 1.87 |
| 0.6B | FinanceBench | 415,929 | 42,223 | 2,617 | 8.8M | 0.30 |
| 4B | FreshStack | 264,317 | 12,671 | 7,390 | 12.0M | 0.90 |
| 4B | BioASQ | 50,784 | 7,664 | 7,390 | 14.4M | 2.07 |
| 4B | FinanceBench | 415,929 | 15,188 | 7,390 | 8.8M | 0.40 |
| 8B | FreshStack | 264,317 | 8,846 | 11,618 | 12.0M | 1.01 |
| 8B | BioASQ | 50,784 | 5,966 | 11,618 | 14.4M | 2.21 |
| 8B | FinanceBench | 415,929 | 10,392 | 11,618 | 8.8M | 0.48 |

Method: full-corpus tokens come from Part C (`token-counts.json`; FinanceBench scaled from the slice by page count, 12,013 pages). Embedding time is full tokens divided by the slice rate. Parsing and per-file overhead come from the 4B rows of this session only (Experiment 48 ran before the in-process Magika change, ADR-117) and scale by file or page count. Estimate only; the smoke run's ingest timings refine it.

Total per full index build of the three corpora: 0.6B 2.9 h, 4B 3.4 h, 8B 3.7 h. Per-file overhead, not embedding, is the largest share. Four index builds (4B baseline, 0.6B, 8B, chunking off) plus one 4B rebuild check need about 17 h before answers and judging.

Decision (task 1.5): run on one rented RTX 4090, secure cloud (archived change `pre-exp35-harness-and-answer-fixes`, design D9). The local judges need the GPU, and every arm of one dataset runs on one machine. The 4B fits, so the hosted `qwen/qwen3-embedding-4b` fallback is not used. The Mac was not timed.

## 5. Steps

Run every command from the repository root. The harness scripts are built by change tasks 2.1 to 2.10 before the freeze.

1. Prepare the data: not a script. The datasets are already on disk and checked (section 4.1); the pod setup copies them and checks their SHA-256.
2. Start OMRS's managed router (`llama-server`) on `127.0.0.1` (scratch port) with one preset per model of the runtime table.
3. Run, per dataset and stage in order (`ingest`, `search`, `answer`): `uv run --no-sync python experiments/35-full-rag-benchmark-2026-11-01/run_arms.py --dataset DATASET --arm all --stage STAGE --run N --resume --answer-host HOST --judges clef_flash,granite_guardian,chat` (six arms, three datasets, 3 runs; `ingest` runs once per index; appends the run record and writes JSONL traces).
4. Determinism check: the same command with `--stage determinism` (runs 2 and 3 against run 1; only a retrieval difference fails it). The 4B rebuild check per dataset is not built yet; it is built before the freeze (Exp 35 task 4.2).
5. Summarise: not built yet. Before the freeze, a summary script applies the `plan.json` statistics with `experiments/_lib/stats_d6.py` and writes `output/summary.json` and the report tables (Exp 35 task 4.2).

The smoke subset (task 4.1) runs a small slice of each dataset through every arm before the freeze and is never scored as a result.

## 6. Analysis

- **Stats level**: expert.
- **Tests** (amended by A2, section 0.10): one linear mixed model per dataset with planned contrasts and Holm across all H1 to H8 contrasts of the dataset; paired permutation test (10,000 shuffles, seed 20261101) and paired bootstrap (10,000 resamples; FinanceBench by document) as robustness checks. Search scores come from one run per setup; answer scores average the 3 runs per question first. McNemar's exact test for hit@page hit or miss. Wilson intervals for rates. Functions come from `experiments/_lib/stats.py`, `stats_d6.py` and the `statsmodels` wrapper `stats_mixed.py`; no new estimator code.
- **Minimum detectable effect**: computed from data before the freeze (section 0.10). The earlier figures (about 4 and 2 points) are withdrawn.
- **Sensitivity**: dropped by A2 (2026-11-13). The 0.045 and 0.055 re-test of the cut-off is not run.
- **Gates**:

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | For the 15 answer setups (A3), the retrieval of answer runs 1, 2 and 3 equals the single search-stage run of the same setup (section 0.7; search runs once per setup) | A mismatch breaks the paired design and is itself a finding |
| G2 | The `e4b-c1024` index rebuilt once per dataset in a fresh process gives the shared index's lists with `e4b-c1024-roff-hoff` | Shows index building is repeatable |
| G3 | `verify_llamacpp_runtime` passes before the first score of every run | A wrong build or file hash invalidates every score |

- **Stop rule**: the run is complete when every search setup has its one run, every answer setup and dataset has 3 runs, the closed-book run, the determinism and rebuild checks, and the Ragas pass. Stop early when the preflight fails, a gate fails, or the projected spend reaches the ceiling of section 0.10. A determinism mismatch is recorded and reported, never swapped for another run.
- **What each outcome means**:
  - Pass: gates hold; the report states each arm's difference or "no difference larger than the minimum detectable effect". (Superseded by A3 and A4: a non-significant result means no difference was detected at this sample size.)
  - Fail: a gate failed; investigate before any number is cited in the paper.
  - Unclear: an interval crosses zero; report it as not shown, not as no effect.

## 7. Runtime

- **Purpose**: publication. **Runtime under test**: no.
- **Local models**: every one runs through llama.cpp on OMRS's managed router (`llama-server`, one preset per model). No Ollama, no MLX. Build b11941 exactly (readiness flow task 5.2); another build needs a plan amendment first. `plan.json` holds the same rows.

| Role | Repository | File | SHA-256 | Build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Embedding baseline 4B | `Qwen/Qwen3-Embedding-4B-GGUF` | `Qwen3-Embedding-4B-Q8_0.gguf` | `b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d` | 11941 | `--embeddings --pooling last --ctx-size 8192 --batch-size 8192 --ubatch-size 8192` |
| Embedding 0.6B | `Qwen/Qwen3-Embedding-0.6B-GGUF` | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` | 11941 | as baseline |
| Embedding 8B | `Qwen/Qwen3-Embedding-8B-GGUF` | `Qwen3-Embedding-8B-Q8_0.gguf` | `d20ddc71e8a5c4344f2343481e242233a997dc5eaff442427a945836c97b4deb` | 11941 | as baseline |
| Claim checker, Clef-Flash | `ggml-org/Clef-Flash-GGUF` | `Clef-Flash-Q8_0.gguf` | `25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e` | 11941 | `--ctx-size 32768 --batch-size 32768 --ubatch-size 32768 --parallel 1` |
| Claim checker, Granite Guardian (superseded by A1: dropped) | `ibm-granite/granite-guardian-3.3-8b-GGUF` | `granite-guardian-3.3-8b-Q8_0.gguf` | `356fc80d343a699a3d12316de161d4341ee2d11f7057123dabb158804e876bc5` | 11941 | as Clef-Flash |

(Superseded by A1: the ONNX reranker is gone; every reranker runs on llama.cpp.) The ONNX reranker and the OCR engines do not run through llama.cpp. The freeze records them under the runtime manifest with name, revision and file hash. The embedding tokenizer (`Qwen/Qwen3-Embedding-4B`, `tokenizer.json`, revision `5cf2132a`) is the token-aware chunking tokenizer, cached and hash-checked by sweep task 2.4a.

- **Hosted references** (section 3, ADR-119): answer model `deepseek/deepseek-v4.1-flash-1017` (OpenRouter, temperature 0, seed 20261101, one pinned upstream host); main Ragas judge `openai/gpt-oss-120b` (OpenRouter, reasoning `low`, temperature 0, fixed seed, one pinned upstream host); cross-check judge `openai/gpt-6.1-terra` (OpenRouter, fixed seed, 50 hand-checked items; superseded by A4: removed); main claim checker GLM-5.3 (Z.AI, section 4.4). A judge never scores its own model family.
- **Tolerance**: 0.005 absolute on nDCG@10, the only primary metric, and on the secondary Recall@10, MRR@10 and hit@page (A2; nDCG@10 only is primary). The largest change that still counts as the same result on another back end. Confirm or change at freeze.
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score of each run and passes `runtime=found.as_run_record()` to `record_run_start`. A mismatch stops the run.
