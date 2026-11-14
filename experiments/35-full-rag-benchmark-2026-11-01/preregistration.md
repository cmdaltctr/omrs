# Experiment 35 pre-registration: reproducible local RAG benchmark of OMRS

## 1. Status and governing rule

- **Date**: 2026-11-14 (amendment A4). Written before the freeze. No measured run has started.
- **This file governs Experiment 35.** It holds the live design only, with no history. Where it and any other file disagree (`protocol.md`, `plan.json`, the OpenSpec changes, the proposal), this file wins. It is the main file of the OSF deposit.
- **The proposal** `docs/proposals/first-publication-benchmark.md` stays the master plan for scope, order of work, Part 2 (RAGFlow) and E1 (EnterpriseRAG-Bench). Its Experiment 35 design facts must match this file.
- **Part 2 and E1.** Section 18 wins over the proposal for the points it fixes: the OMRS setup and its hash, the halves, the shared parts, the measurement settings, the C1 and C2 measures and tests, and the Part 2 missing-outcome rules. The proposal governs every other Part 2 and E1 fact until the Part 2 protocol is frozen. After that, the Part 2 protocol governs them.
- **History**: `protocol.md` sections 0.1 to 0.13 (amendments A1 to A4) and sections 1 to 7 hold earlier plans and their reasons. They are not live design.
- **Study type**: confirmatory benchmark, purpose `publication`. OSF data category (OSF Prereg form): registration before analysis of the outcome data. Some outcome data exist before the freeze. Index builds and search are deterministic (G2), so the MDE pilot's retrieval scores on half A equal main-run outcome data for the pilot cells. Smoke and test-pod answers also exist. Section 5 lists every earlier look at the data.
- **Task pointers.** "RDY task n" is task n of the OpenSpec change `exp35-main-run-readiness`. "C35 task n" is task n of `experiment-35-full-document-rag-benchmark`. "FLOW step n" is step n of `rag-benchmark-readiness-flow`.

## 2. Research questions

- **RQ1 (absolute performance).** What retrieval and answer quality does OMRS reach on FinanceBench, FreshStack, BioASQ and (exploratory) Legal RAG Bench, under the stated models and settings? Answered by the headline of section 14.3.
- **RQ2 (component effects).** How do embedder size, chunk size, reranker size and hybrid search change retrieval quality? How does chunk size change answer faithfulness and correctness? Answered by H1 to H8b.
- **RQ3 (external comparison).** Part 2 and E1. Section 18 gives what Experiment 35 fixes for them and wins over the proposal on those points (section 1).

**Scope S.** Every hypothesis holds only within this scope: Qwen3-Embedding and Qwen3-Reranker models at Q8_0 on llama.cpp build b11941; English text; queries embedded with no query instruction; the reranker's default instruction; one hosted answer model; the four datasets as built in section 4. No claim extends past scope S.

## 3. Factors, levels and setups

| Factor | Levels |
| --- | --- |
| Embedder | Qwen3-Embedding 0.6B, 4B, 8B (Zhang et al. 2025) |
| Chunk size | 512, 1,024, 2,048 Qwen3 tokens; overlap 15% (77, 154, 307 tokens) |
| Reranker | Off, Qwen3-Reranker 0.6B, 4B, 8B (llama.cpp `/v1/rerank`) |
| Hybrid | Off (dense only), or BM25 plus dense with RRF fusion |

- **Search stage.** Full factorial: 9 indexes (`e<embedder>-c<chunk size>`) and 72 search setups (`e<embedder>-c<chunk size>-r<reranker>-h<hybrid>`) per dataset. Each setup runs once on its sealed index. Each index is built once (one-build-per-cell assumption, section 15).
- **Fixed in search.** Every setup saves its top 100 chunks (`top_k` 100, `fetch_k` 100, so the rerank pool is exactly 100 and the reranker returns all 100 in order). `similarity_threshold` 0.0. Metadata extraction `disabled`. All datasets go through the Markdown splitter and count tokens with the pinned Qwen3 tokenizer (revision `5cf2132a`). BioASQ and Legal passages are written as `.md`. Dense search is exact: no approximate vector index is built.
- **Answer stage.** 15 answer setups at the embedder and reranker size chosen on half A (section 14.1): 12 crossed setups (chunk size 3 x reranker on or off x hybrid on or off), each with 10 chunks of evidence; and 3 token-matched setups `c512-t20k`, `c1024-t20k`, `c2048-t20k` (reranker on, hybrid on), each with evidence cut at 20,480 real Qwen3 tokens. The `c2048` x 10 crossed cell keeps its 10 chunks. Each answer setup runs 3 times on all 1,160 questions.
- **Token cut.** Chunks are taken in rank order and their Qwen3 token counts are summed. A chunk is included when the total before it is below 20,480. The chunk that crosses the limit is truncated at the limit, and no later chunk is included. Truncation is recorded per question.
- **Other runs.** Two closed-book runs, one oracle run (section 13), and a length-controlled checker run (section 11.2).

## 4. Datasets

| Dataset | Questions | Corpus | Gold unit | Role |
| --- | ---: | --- | --- | --- |
| FinanceBench open sample (`PatronusAI/financebench`; Islam et al. 2023) | 150 | 84 PDFs, 12,013 pages, read to Markdown by `pdf-inspector` 1.17.0 | Page (189 evidence items) | Core, confirmatory |
| FreshStack LangChain (`freshstack/queries-oct-2024`, `freshstack/corpus-oct-2024`, config `langchain`; Thakur et al. 2025) | 203 | Full public corpus, 49,514 documents | Document | Core, confirmatory |
| BioASQ mini (`enelpol/rag-mini-bioasq`, test split) | 707 | 40,181 passages (`text-corpus/test`) | Passage | Core, confirmatory |
| Legal RAG Bench (`isaacus/legal-rag-bench`) | 100 | 4,876 passages | Passage (one per question) | Exploratory |

- **FreshStack corpus.** All 9 FreshStack indexes are built on the full public LangChain corpus at a pinned revision (pre-freeze task P1). The download needs the user's approval at build time. The 10,000-document subset used in Experiments 9a and 22 (all 1,547 gold documents plus 8,453 random distractors) is retired for Experiment 35. The 20 Experiment 9 continuity queries, 15 continuity documents and the overlay runbook are not used. No result is compared with the FreshStack leaderboard unless the same corpus and metric are used.
- **Revisions and hashes.** FinanceBench revision `e04404e3a97f69f79c14d42f24981a1c9c3bcd18`, PDFs at commit `cc39aeb4afdf33909ee1412188bf89035950c2eb`; BioASQ revision `8a845907dc1cff31d42fa6f7bb9c6eef5f3ae6f6` (`protocol.md` section 4.1). FreshStack and Legal revisions: section 16.
- **Licences.** FinanceBench CC BY-NC 4.0; FreshStack CC BY-SA 4.0; BioASQ CC BY 2.5 with the NLM terms notice; Legal RAG Bench CC BY-NC-SA 4.0. Source checks: `protocol.md` section 4.2. Release rules: section 19.
- **Halves A and B.** Each dataset is split into half A and half B with seed 20261115 (`halves.json`, SHA-256 recorded at the freeze). FinanceBench is split by document: documents are shuffled with the seed and each goes, with all its questions, to the half that has fewer questions so far (ties to A). No FinanceBench document sits in both halves. FreshStack, BioASQ and Legal are split by question: questions are shuffled with the seed, and the first half (rounded up) is half A.
- **Use of the halves.** Half A feeds every selection step (section 14) and every pre-freeze sample drawn after `halves.json` exists (the MDE pilot, RAGFlow checks). Samples drawn earlier (smoke runs, test pod, classifier-gate claims) are listed in section 5 with their question IDs, and with their half once `halves.json` exists (P12). No selection step reads half B, so selection bias stays out of the half-B scores (Cawley and Talbot 2010). Half-B scores are computed only after the A3 configuration hash is time-stamped (section 14.2). H1 to H8b use all questions.

## 5. Existing data

| Data seen before the freeze | What was seen | Effect on this study |
| --- | --- | --- |
| FreshStack queries and qrels in Experiments 9a and 22 | Per-query nDCG@10 of Qwen3-Embedding-4B on the retired 10,000-document subset; 223 queries (203 public) | Queries and gold labels were seen; the full corpus was not. Experiment 22 values do not feed the MDE table. |
| Experiment 10 reranker result | The reranker then in use lowered technical-workload retrieval by 19 to 27% (repository `AGENTS.md`) | H2 predicts the reranker helps, set with this result known. Experiment 35 uses Qwen3-Reranker on llama.cpp. |
| Smoke runs (H-CC smoke and FreshStack rerun, 2026-11-11) | Answers and claims for 15 questions: BioASQ 4043, 1372, 604, 2291, 1122; FinanceBench `financebench_id_01476`, `_01964`, `_01484`, `_05718`, `_00476`; FreshStack 76404464, 78048414, 77762811, 77828572, 77536364 | Answers were read; 10 smoke claims were practice-labelled. The half of each ID is listed once `halves.json` exists (P12). |
| Factorial smoke run (FLOW step 6.10) and test pod session | 5 seeded questions per dataset, answers and retrieval | IDs and halves recorded at the freeze (P12). Never scored as results. |
| MDE pilot (section 10) | Retrieval scores of 40 seeded half-A questions per core dataset | Half A only. No selection is made from it. |
| Checker selection runs | LLM-AggreFact test split (external data) and smoke claims | The own-claims guard limits were set after the smoke data were seen (`protocol.md` section 4.4). |
| Experiment 48 timing | Embedding speed on slices of FreshStack, BioASQ and FinanceBench | Timing only, no scores. |

## 6. Metrics

**Unit scoring.** Each setup's top 100 chunks map to units (FinanceBench page, FreshStack document, BioASQ or Legal passage). The first occurrence of each unit is kept in rank order, and the list is cut at 10 units. On FinanceBench a chunk counts for its first page (primary); any-page credit is a sensitivity analysis. Relevance is binary. Every question has at least one gold unit.

For question q with gold set G_q (size R_q) and unit list L_q of up to 10 units, rel_i = 1 when unit i of L_q is in G_q (missing ranks count as 0). Following the trec_eval convention, every metric is a plain mean over the questions of a dataset:

- DCG@10 = sum over i = 1 to 10 of rel_i / log2(i + 1).
- IDCG@10 = sum over i = 1 to min(R_q, 10) of 1 / log2(i + 1).
- nDCG@10 = DCG@10 / IDCG@10. **Primary metric of the study.**
- Recall@10 = |L_q intersect G_q| / R_q.
- MRR@10 = 1 / (rank of the first gold unit in L_q), else 0.
- hit@page (FinanceBench) = 1 when any gold page is in L_q.
- **`evidence_recall_20k`** = share of G_q covered by the evidence taken from the top 100 chunks under the token cut of section 3. **Any-page credit:** a whole chunk covers every gold page it overlaps; a truncated crossing chunk covers only its first page, because the reader stores no page offsets inside a chunk. On FreshStack, BioASQ and Legal a chunk, whole or truncated, covers its one unit. First-page credit is a registered sensitivity analysis. **Confirmatory endpoint for H6 and H7 on FinanceBench (rows 9 to 11).** `plan.json` flags both nDCG@10 and `evidence_recall_20k` as `primary`, because there the flag marks a metric that a primary hypothesis's decision rests on (the guide asks for a tolerance per primary metric); it does not mark a second headline metric.
- **alpha-nDCG@10** (FreshStack, secondary): computed with the benchmark's own scorer if its nugget labels allow (P3); otherwise reported as not available.

**Answer metrics.** Per answer, then averaged over the 3 runs per question, then over questions.

- **Faithfulness** (`faithfulness_glm_factual`): share of the answer's factual claims (classifier kinds fact and mixed) that GLM-5.3 calls supported. Refusal claims are reported apart. Claims and citations come from the answer itself: the answer model cites evidence by ordinal (for example `[1]`), the saved answer is split into claims, only prose segments with at least one valid ordinal go to the checker, and the checker sees one claim with the text of the evidence its ordinals cite (OpenSpec specs `grounded-answer-synthesis` and `benchmark-answer-scoring`).
- **Correctness** (`ragas_answer_correctness`): Ragas 0.4.3 (Es et al. 2023) `AnswerCorrectness`, default weights (factual 0.75, similarity 0.25), judge `openai/gpt-oss-120b`, local 4B embedder. The judge sees the question, the answer and the reference answer, never the contexts. FreshStack's reference is `answer_text` (the accepted Stack Overflow answer).
- **Secondary**: Clef-Flash faithfulness, FinanceBench number match (`protocol.md` section 0.6 rule), refusal rate, the four other Ragas metrics, closed-book and oracle correctness.

## 7. Hypotheses

Each null is a zero effect. Every test is two-sided. A directional contrast counts when its Holm-adjusted p is below 0.05 and its estimate has the predicted sign (this is a one-sided test at 0.025). A two-sided contrast counts when its Holm-adjusted p is below 0.05. A two-sided hypothesis holds only when the same row counts with the same sign on every dataset its rule needs. Rows that count with opposite signs are reported as a dataset-dependent effect, and the hypothesis does not hold. The report always states the direction. Marginal contrasts weight every cell of the other factors equally (for example, the embedder effect averages over 24 cells, 18 of them reranker-on). Row numbers refer to section 8.

- **H1 (embedder).** Within scope S, a bigger embedder ranks gold units higher. Rows 1 (4B minus 0.6B) and 2 (8B minus 4B), nDCG@10, directional. Null: each contrast is zero. Holds: each step holds when its row counts on at least 2 of the 3 core datasets. H1 holds in full when both steps hold, in part when one does.
- **H2 (reranker).** Within scope S, the reranker raises nDCG@10. Row 3 (mean of the three reranker sizes minus off), directional. Null: zero. Holds when row 3 counts on at least 2 of 3 core datasets.
- **H3 (hybrid).** Within scope S, hybrid search raises nDCG@10. Row 4, directional. Null: zero. Holds as H2.
- **H4 (combining reranker and hybrid: simple effects).** Within scope S, reranker plus hybrid beats each alone. Row 5 (both on minus reranker only) and row 6 (both on minus hybrid only), directional. These are simple effects, not an interaction test; the interaction is reported descriptively with its interval. Null: each contrast is zero. Holds on a dataset when both rows count there; holds overall on at least 2 of 3 core datasets.
- **H5 (reranker size).** Within scope S, a bigger reranker ranks better (reranker-on setups). Rows 7 (4B minus 0.6B) and 8 (8B minus 4B), directional. Holds as H1.
- **H6 (chunk size, search).** Within scope S, chunk size changes retrieval. Rows 9 (1,024 minus 512) and 10 (2,048 minus 1,024), two-sided. Endpoint: `evidence_recall_20k` on FinanceBench, nDCG@10 on FreshStack. Null: each contrast is zero. Holds when the same row (9 or 10) counts with the same sign on FinanceBench and on FreshStack. BioASQ is a sanity check (most passages are shorter than 512 tokens, so chunk size barely changes its chunks); Legal is exploratory. FinanceBench sensitivity: nDCG@10 with first-page and with any-page credit; the report gives sign agreement per row.
- **H7 (embedder by chunk size).** Within scope S, a bigger embedder gains more from bigger chunks. Row 11: (8B at 2,048 minus 8B at 512) minus (0.6B at 2,048 minus 0.6B at 512), marginal over reranker and hybrid, directional, with the H6 endpoints. Null: zero. Holds when row 11 counts on both FinanceBench and FreshStack. BioASQ is a sanity check, Legal exploratory. Expected to be underpowered (section 10).
- **H8a (chunk size with context length, answers).** Within scope S, chunk size changes faithfulness and correctness in the 12 crossed setups, where context length grows with chunk size (long contexts can hide evidence: Liu et al. 2024). Rows 12 to 13 (faithfulness) and 14 to 15 (correctness): 1,024 minus 512 and 2,048 minus 1,024, marginal over reranker and hybrid, two-sided. Expected direction for faithfulness: falls as chunks grow (Wang et al. 2024); the report gives the sign. Null: each contrast is zero. Per outcome, holds when the same row counts with the same sign on FinanceBench and on FreshStack. Legal is exploratory. BioASQ chunks barely change with chunk size, so BioASQ rows 12 to 19 are sanity checks, like rows 9 to 11 (section 8). This rule depends on open item O6.
- **H8b (chunk size at equal tokens, answers).** Within scope S, chunk size changes faithfulness and correctness when evidence is held at 20,480 tokens. Rows 16 to 17 (faithfulness) and 18 to 19 (correctness): `c1024-t20k` minus `c512-t20k` and `c2048-t20k` minus `c1024-t20k`, two-sided, at reranker on and hybrid on with the chosen sizes (so H8b is conditional on that cell). Holds as H8a (per outcome, the same row counts with the same sign on FinanceBench and on FreshStack). **Reading fixed now:** "chunk size itself changes X" is claimed only when H8b holds for outcome X. When H8a holds and H8b does not, the claim is "chunk size together with context length changes X".

**Error rates of the composite rule.** Holm within each dataset plus "at least 2 of 3 datasets" (H1 to H5) or "FinanceBench and FreshStack" (H6 to H8b) is conservative. Under the null on three independent datasets, a false "holds" for one directional contrast has probability about 3 x 0.025 squared, about 0.002, before Holm. Under the FinanceBench-and-FreshStack rule it is about 0.025 squared (about 0.0006) for a directional row, and 2 x 0.025 squared (about 0.001) for a two-sided row under the same-sign rule. Power falls the other way: at a per-dataset power of 0.6, the 2-of-3 rule has about 0.65; at 0.5, about 0.50.

## 8. Contrast table and Holm families

Contrasts are per question, marginal over every factor not named. Search rows use all 72 setups; H8a rows use the 12 crossed setups; H8b rows use the 3 token-matched setups. FB is FinanceBench, FS FreshStack, BQ BioASQ.

| Row | Hyp. | Contrast | Sign | FB endpoint | FS endpoint | BQ |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | H1 | e4b minus e0.6b | + | nDCG@10 | nDCG@10 | family |
| 2 | H1 | e8b minus e4b | + | nDCG@10 | nDCG@10 | family |
| 3 | H2 | mean(r0.6b, r4b, r8b) minus roff | + | nDCG@10 | nDCG@10 | family |
| 4 | H3 | hon minus hoff | + | nDCG@10 | nDCG@10 | family |
| 5 | H4 | (reranker on, hon) minus (reranker on, hoff) | + | nDCG@10 | nDCG@10 | family |
| 6 | H4 | (reranker on, hon) minus (roff, hon) | + | nDCG@10 | nDCG@10 | family |
| 7 | H5 | r4b minus r0.6b | + | nDCG@10 | nDCG@10 | family |
| 8 | H5 | r8b minus r4b | + | nDCG@10 | nDCG@10 | family |
| 9 | H6 | c1024 minus c512 | two-sided | `evidence_recall_20k` | nDCG@10 | sanity |
| 10 | H6 | c2048 minus c1024 | two-sided | `evidence_recall_20k` | nDCG@10 | sanity |
| 11 | H7 | (e8b c2048 minus e8b c512) minus (e0.6b c2048 minus e0.6b c512) | + | `evidence_recall_20k` | nDCG@10 | sanity |
| 12 | H8a | c1024 minus c512 | two-sided | faithfulness | faithfulness | sanity |
| 13 | H8a | c2048 minus c1024 | two-sided | faithfulness | faithfulness | sanity |
| 14 | H8a | c1024 minus c512 | two-sided | correctness | correctness | sanity |
| 15 | H8a | c2048 minus c1024 | two-sided | correctness | correctness | sanity |
| 16 | H8b | c1024-t20k minus c512-t20k | two-sided | faithfulness | faithfulness | sanity |
| 17 | H8b | c2048-t20k minus c1024-t20k | two-sided | faithfulness | faithfulness | sanity |
| 18 | H8b | c1024-t20k minus c512-t20k | two-sided | correctness | correctness | sanity |
| 19 | H8b | c2048-t20k minus c1024-t20k | two-sided | correctness | correctness | sanity |

"Reranker on" in rows 5 and 6 is the mean over the three reranker sizes. BioASQ uses nDCG@10 for rows 1 to 8.

**Family sizes, fixed now.** FinanceBench: 19 (rows 1 to 19). FreshStack: 19 (rows 1 to 19). BioASQ: 8 (rows 1 to 8). Legal RAG Bench: no family; all 19 rows are exploratory. In all, 46 contrasts sit in Holm families. BioASQ rows 9 to 19 are sanity checks, reported with unadjusted 95% intervals and no decision. The reason is the same for all of them: most BioASQ passages are shorter than 512 tokens, so chunk size barely changes BioASQ chunks. Rows 12 to 19 as sanity checks depend on open item O6.

**Gated rows stay in the family.** No gate changes a family size. A row whose measure fails its gate (section 11), or that the differential-error rule makes exploratory, stays in its family with p = 1 and is reported as "not testable". With p = 1 it takes the last Holm rank, so the other rows keep the same number of comparisons.

## 9. Analysis model

One clustered method gives every estimate, interval and p-value. There is no mixed model.

1. **Per-question contrast score.** For row k and question q, d_qk is the mean of question q's scores over the cells at the first level minus the mean over the cells at the second level (equal cell weights). Answer scores are first averaged over the 3 runs.
2. **Estimate.** The plain mean of d_qk over the questions that enter the row (section 12).
3. **FreshStack, BioASQ and Legal.** The decision test is defined by its closed form. Let n be the number of questions that enter the row and r_q = d_qk minus the estimate. Estimate: the mean of d_qk. Variance: (sum of r_q squared) x (n / (n minus 1)) squared / n squared. Reference distribution: t on n minus 1 degrees of freedom, for the p-value and the 95% interval. This is the Mancl and DeRouen (2001) bias-reduced sandwich for an intercept-only model with one row per cluster. It equals the paired t-test variance times n / (n minus 1), so it needs no convergence fallback. With complete data the estimate equals the cell-means contrast of the full-factorial model. **Implementation:** `statsmodels` GEE (Liang and Zeger 1986) of d_qk on an intercept (Gaussian family, identity link, independence working correlation, clusters = questions, `cov_type="bias_reduced"`) gives the estimate and the variance. The p-value and the interval are always computed from the t reference above, whatever reference the library reports by default. A known-answer test (RDY task 15.6) checks that the library estimate and variance equal the closed form. If they do not, the closed form is used and the difference is reported.
4. **FinanceBench (questions share documents).** The decision p-value comes from a document-level sign-flip permutation test. The statistic is the question-weighted mean of d_qk. Under the null, the sign of each document's sum of d_qk is flipped at random: 100,000 draws, seed 20261101, p = (1 + number of draws with an absolute statistic at least as large) / 100,001. The 95% interval inverts the same test (the set of shifts not rejected at 0.05, with the same draws). The test assumes each document's sum is symmetric about zero under the null. The interval also assumes a constant additive shift for every question (a location-shift model); the point estimate and the p-value do not need it.
5. **Decision.** Holm (alpha 0.05) within each family (Carterette 2012) on the decision p-values, then the sign rule of section 7, then the 2-of-3 or both-datasets rule of each hypothesis (with the same-sign rule of section 7 for two-sided rows).
6. **Sensitivity checks, registered, never decisive.** FreshStack and BioASQ: paired permutation test by question (10,000 shuffles, seed 20261101; Smucker, Allan and Carterette 2007; Urbano, Lima and Hanjalic 2019). FinanceBench: the GEE of point 3 with document clusters. Every row where the decision and the sensitivity check disagree on "counts" is listed in one table.
7. **Search-stage scores** come from one run per setup. **Intervals** printed beside Holm decisions are unadjusted 95% intervals (Miller 2024).

A non-significant result means no difference was detected at this sample size. The study makes no equivalence claim and runs no TOST.

## 10. Power, minimum detectable effect and smallest effect of interest

- **Smallest effect of interest (SESOI).** 0.02 nDCG@10 (OPEN item O2: the user confirms the value; Lakens 2017). Each row's interval is reported against plus and minus the SESOI. No other endpoint has a SESOI; their intervals are reported against the MDE.
- **Pilot.** Retrieval only, before the freeze: 40 seeded half-A questions per core dataset (seed 20261118), on full-corpus indexes, through a cell list fixed before the pilot runs (P5). No hosted calls. The pilot builds at most 4 indexes per core dataset: the four H7 corner cells (`e0.6b-c512`, `e0.6b-c2048`, `e8b-c512`, `e8b-c2048`). Reranker and hybrid setups run on those indexes as the cell list needs. A contrast between adjacent levels (for example 4B minus 0.6B) uses the SD of the extreme-level contrast (8B minus 0.6B) as a stand-in, and the MDE table says so. Pilot indexes are built with the pinned models and settings and are not reused: the main run builds all 9 indexes after the freeze. The pilot gives the SD of per-question contrast scores per dataset and contrast type, and on FinanceBench the design effect of document clustering. Experiment 22 values are not used.
- **Pilot cost.** The pilot cost is projected from the P2 timing, added to the estimate before the freeze and shown in the compute table (section 17). The user approves it before the pod starts. Registered fallback if the user declines: no pilot; the MDE table is filled as a range from assumed SDs of 0.15 to 0.25 for retrieval contrasts, labelled as assumed, and the report says H7 and Part 2 C2 are expected to be underpowered.
- **MDE.** MDE = (z at 1 minus alpha/2 plus z at 0.80) x SD / square root of n, with alpha = 0.05 / family size (worst Holm rank: 0.05/19 on FinanceBench and FreshStack, 0.05/8 on BioASQ) and n divided by the design effect on FinanceBench. Answer-stage rows use the SD from named smoke and test-pod answer files (P6) and are labelled rough.

| Dataset | Row(s) | SD of d (source) | MDE | Below SESOI? |
| --- | --- | --- | --- | --- |
| (filled by P5 and P6 before the freeze) | | | | |

- **Known weak spots (reviewer estimates, to be replaced by the table).** H7 compares differences of differences of single cells; at plausible SDs its MDE on FreshStack is about 0.08 to 0.12 nDCG@10, so H7 is expected to be underpowered. Part 2 C2 on half B is expected to detect only large correctness differences. The report states both.

## 11. Judges, checkers and human labels

### 11.1 Models

- **Main claim checker**: GLM-5.3 (Z.AI Coding Plan endpoint, `chat`, reasoning `low`, temperature 0, seed 20261109). **Second checker**: Clef-Flash (local GGUF). If Clef-Flash fails its faithfulness gate, its results are reported as not validated and it changes no confirmatory row. The runner never switches checker itself; a failed call stops the stage and `--resume` retries it. If GLM-5.3 is withdrawn before the run ends, that is a deviation (section 20).
- **Checker tolerance.** A local checker may replace the main one only under the rule of `protocol.md` section 4.4. Its 2-point allowance is restated against the H8a and H8b faithfulness MDE once the MDE table is filled: the bar stays only if it is at most half that MDE (P7). The withdrawn "about 4 points" figure is not used.
- **Claim classifier**: `openai/gpt-oss-120b` sorts claims into fact, refusal or mixed. Pre-freeze gate: agreement at least 0.90 and refusal recall at least 0.90 on 100 L1-labelled smoke claims (seed 20261112).
- **Ragas judge**: `openai/gpt-oss-120b` (reasoning `low`, temperature 0, one pinned upstream host). Its seed, and the classifier's seed, are pins still to record (P10). There is no cross-check judge: `openai/gpt-6.1-terra` is removed, because no cost estimate includes it.

### 11.2 Gates

Gate decisions are computed and recorded, with a time, before any H8 contrast result is computed.

**Interval method for every gate.** Every gate interval (kappa, the AUC lower bound, the specificity difference) is a percentile bootstrap: 10,000 resamples, resampling by question, so all claims or answers of one question move together. Each interval has its own seed (section 16).

- **Faithfulness gate, per checker.** Cohen's kappa (Sim and Wright 2005) of the checker against the human label: point estimate at least 0.60 and lower 95% bound at least 0.40. Sample: 450 claims from the crossed setups, 150 per chunk size, 50 per core dataset within each chunk size, at most one claim per answer, seed 20261116. The claims are drawn from answers to all questions (both halves), because H8a and H8b are tested on all questions. The correctness sample below stays on half B. The gate is pooled over the three core datasets because 150 claims per dataset are too few for a per-dataset gate; kappa per checker and per core dataset is reported with its interval as descriptive and decides nothing. "Can't tell" counts as not supported (the binary benchmark scale); kappa is also reported with "can't tell" items left out. If GLM-5.3 fails, rows 12, 13, 16 and 17 are not testable on every dataset.
- **Differential-error rule.** "Unsupported" is the positive class. Specificity is the share of human-supported claims the checker calls supported. The rule uses GLM-5.3, the main checker; Clef-Flash specificity is reported only. If the 95% interval of the GLM-5.3 specificity difference (2,048 minus 512) excludes zero in either direction, H8a and H8b faithfulness (rows 12, 13, 16, 17) is exploratory and not testable. Sensitivity per chunk size is reported.
- **Correctness gate, per core dataset.** 50 questions per core dataset drawn from half B (seed 20261113); for each question, one answer from run 1 of an answer setup chosen uniformly at random by the same seed. 50 Legal answers, drawn the same way, are also labelled and reported without a gate. The Ragas score is cut at 0.5 (fixed before labelling). The gate passes on a dataset when kappa is at least 0.60 with a lower 95% bound of at least 0.40, computed with "can't tell" items scored both as correct and as not correct (both must pass). The continuous score is validated too: its AUC against the human label must have a lower 95% bound above 0.5. If the gate fails on a dataset, rows 14, 15, 18 and 19 are not testable there. Prevalence, raw agreement and PABAK are reported beside kappa (Feinstein and Cicchetti 1990; Byrt, Bishop and Carlin 1993).
- **Length-controlled check (registered sensitivity, no gate).** 300 claims from `c2048` crossed answers (seed 20261119). GLM-5.3 and Clef-Flash judge each claim again against one 512-token window of each cited chunk: the chunk is split into consecutive 512-token windows, and the window that shares the most distinct lower-case claim words is kept (ties go to the earlier window). The report gives the verdict change rate with a Wilson interval.

### 11.3 Human labels

- **Labellers.** L1 is the operator, an OMRS author. L2 is a second labeller (OPEN item O4: name, role and relation to the project; recorded in the run record, never in public files). L2 labels a 30% subset of each set (seeds 20261122 to 20261124, one per set; section 16). Kappa of L1 against L2 is reported per set with a bootstrap interval (section 11.2 method). Disagreement rule: L1 and L2 discuss; if they cannot agree, the item is "can't tell" and counted.
- **Counts.** L1: claim kinds 100, faithfulness 450, correctness 200; 750 in all. L2: 225.
- **Guidelines.** One written guideline per set (claim kinds, faithfulness, correctness, and Part 2 correctness), with worked examples drawn from outside every sample, fixed before the first label and released (P8). Faithfulness follows the LLM-AggreFact task definition (MiniCheck): a claim is supported if and only if the cited passages support it, judged as the checker sees it, on meaning not grammar.
- **Blinding.** Labellers never see scores, verdicts, setup names or chunk sizes. Cited passage length can still hint at chunk size; the report says so. A training round on practice items comes first and is not evidence.
- **Ethics.** An ethics query goes to the university before the first label (OPEN item O5); the answer is recorded.
- **Conflict of interest.** The authors built OMRS. Safeguards: this pre-registration and its deviation log; selection on half A only; Holm families fixed now; blind labels with L2 as primary labeller in Part 2; published RAGFlow settings and maintainer correspondence; release of every output (section 19). The paper states the conflict.
- **Optional blind relevance audit** for H3 and C1 (about 300 to 400 L1 labels on unjudged top-3 units, seed 20261120): runs only if the user approves (OPEN item O3). It would be descriptive.

## 12. Missing outcomes

Every question stays in its dataset's denominator. Every exclusion is counted per setup and row and printed.

- **Search.** A list shorter than 10 units scores its missing ranks as not relevant. A search row still missing after `--resume` scores 0 and is listed.
- **Failed answer call.** The resend rule applies: a call is resent only when no result was saved, never because of content, and each resend is counted (`resent_calls`). An answer still missing when the run closes scores 0 for correctness and number match, and counts as an answer with no factual claim.
- **Answer with no factual claim.** Faithfulness is undefined for that run. Per question and setup, faithfulness is the mean over the runs that have at least one factual claim. A question enters a faithfulness row only when every cell used by that row has a value (complete cases). Two registered sensitivity analyses keep every question: no-claim answers scored 1, and scored 0. The refusal rate per setup is reported as a co-outcome.
- **Unjudged rows.** Ragas and checker rows that failed are retried on `--resume`. A row still unjudged when the run closes leaves that row's complete cases and is counted; a sensitivity analysis scores it 0.
- **Unclassified claims.** A claim the classifier still fails on after `--resume` is treated as a factual claim: it stays in the faithfulness denominator and is counted. A sensitivity analysis leaves such claims out.
- **Part 2 rules** are in section 18.

## 13. Floor, ceiling and closed-book runs

All are single runs on all 1,160 questions, scored like the main runs, descriptive only, with no hypothesis test. The report says that the main setups average 3 runs and these do not.

- **Closed-book, own-knowledge prompt (floor).** The answer model with no evidence and a fixed prompt that asks for an answer from its own knowledge.
- **Closed-book, RAG prompt.** The main answer prompt with an empty evidence block, so it differs from the RAG setups only in the evidence. A registered sensitivity analysis.
- **Oracle (ceiling).** Gold units given directly as evidence (Legal gold passage, FinanceBench gold page texts, BioASQ gold passages, FreshStack gold documents), capped at 20,480 Qwen3 tokens with truncation recorded. It has no distractors, so it is an upper bound, not a fair comparison.
- **Contamination sensitivity.** Rows 14, 15, 18 and 19 are re-run on the questions that both closed-book runs answer wrongly (Ragas correctness below 0.5). The report gives closed-book correctness per dataset beside every correctness table, and a per-question cross-table on retrieval misses (closed-book correct or not against RAG correct or not).

## 14. Selection rule, order of work and RQ1 headline

### 14.1 Selection (A3), half A only

Pooled score = plain mean of the per-dataset mean nDCG@10 over FinanceBench, FreshStack and BioASQ, on half A. Legal takes no part.

1. **Embedder.** Pooled score per embedder averaged over all other factors. Choose the smallest embedder within 0.01 of the best (a gap of exactly 0.01 counts as within).
2. **Reranker size.** At the chosen embedder, reranker-on setups averaged over chunk size and hybrid. Choose the smallest size within 0.01 of the best. Equal scores go to the smaller size.
3. **A3 cell (for RQ1 and Part 2).** At the chosen embedder and reranker size, the 12 cells (chunk size x reranker on or off x hybrid on or off). A cell ties the best cell when its pooled score is within 0.01 of it. Among tied cells choose, in order: (1) reranker off, (2) hybrid off, (3) the chunk size with the lowest index cost, (4) the smaller chunk size. Each step applies to the cells left by the step before.

- **Index cost** = stored vector values: number of chunks times embedding dimension, summed over the three core datasets. It is known from the sealed indexes before any score.
- **Configuration hash** = SHA-256 of the canonical JSON (keys sorted, no spaces, UTF-8) of the selected cell's resolved settings, with the SHA-256 of `halves.json` as one field.
- `selection.json` records every pooled score, both chosen sizes, the A3 cell and the hash. A sensitivity analysis repeats step 3 with any-page nDCG@10 on FinanceBench and reports whether the cell changes; the registered cell does not change.

### 14.2 Order of work

1. Build and seal the 9 indexes; G2 passes before any search writes into the shared output folder.
2. Run the 72 search setups on all questions.
3. Score half A only. Apply 14.1. Write `selection.json`.
4. Time-stamp the configuration hash with a file upload to the registered OSF project (OPEN item O1: the user confirms the mechanism).
5. Only then score half B, and start the replicate pods (answer stage).

The word "sealed" applies to indexes only. Half B is held out from every selection step; its search lists exist on disk before step 4, but no half-B score is computed before it.

### 14.3 RQ1 headline

- **Retrieval headline**: the A3 cell's nDCG@10 on half B, per core dataset, with its 95% interval. The 72-setup table on all questions is descriptive.
- **Answer headline**: the answer setup that matches the A3 cell, on half B, faithfulness and correctness per dataset with intervals.
- **Search-cost figure**: the expected maximum of the pooled half-A score over n setups drawn at random, adapted from Dodge et al. 2019 (drawn without replacement), computed exactly from the scores sorted in ascending order, v(1) to v(N), as the sum over i = n to N of v(i) x C(i minus 1, n minus 1) / C(N, n). One curve over the 12 A3 cells (n = 1 to 12) and one over the 72 setups (n = 1 to 72). RAGFlow has no point unless its matched search runs (section 18); then RAGFlow gets its own curve over its half-A cells.

## 15. Gates and determinism

| Gate | Pass when |
| --- | --- |
| G1 | For each of the 15 answer setups, the retrieval of answer runs 1, 2 and 3 equals the single search-stage run of that setup. |
| G2 | The `e4b-c1024` index of each dataset, rebuilt in a fresh process, gives the same ranked lists for `e4b-c1024-roff-hoff`. It runs after the seal and before any search writes into the shared output folder. |
| G3 | `verify_llamacpp_runtime` passes for every pinned GGUF file before the first score of every run. |

- **One-build-per-cell assumption.** Each index is built once. Build-time variation is assumed small against the MDEs. G2 covers one index per dataset.
- **Optional rebuild check `e8b-c2048`** on FinanceBench: it runs only if the cost projection after the search stage is at or below the estimate (a cost-only decision). It is reported as the share of identical ranked lists and the nDCG@10 change, not as a gate.
- **Tolerance on another back end**: 0.005 absolute on nDCG@10, Recall@10, MRR@10 and hit@page (`plan.json` `runtime.tolerance`); `evidence_recall_20k` tolerance is task P14.
- A determinism mismatch is recorded and reported, never swapped for another run.

## 16. Pins

| Pin | Value or rule | Where recorded |
| --- | --- | --- |
| llama.cpp build | b11941 exactly | `plan.json` `runtime.models[].build` |
| Embedders 0.6B, 4B, 8B (GGUF, SHA-256, server args) | Q8_0 files | `plan.json` `runtime.models` (roles `embedding-*`) |
| Rerankers 0.6B, 4B, 8B | Pinned after Spearman at least 0.95 against the transformers reference on 200 pairs per size (seed 20261117) | Missing: C35 task 4A.3, RDY task 15.10 |
| Clef-Flash | Q8_0 file and server args | `plan.json` `runtime.models` (role `judge-clef-flash`) |
| Tokenizer | `Qwen/Qwen3-Embedding-4B` `tokenizer.json`, revision `5cf2132a` | `protocol.md` section 0.3; add to `plan.json` (P10) |
| Answer model | `deepseek/deepseek-v4.1-flash-1017`, OpenRouter, temperature 0, seed 20261101, `answer.context_window` 131,072 characters, `answer.max_rounds` 1 | `plan.json` `runtime.references` (model only) |
| Answer model host, reasoning mode, output cap, context length (at least 65,536 tokens) | To record | Missing: P10 |
| Ragas judge and classifier | `openai/gpt-oss-120b`, reasoning `low`, temperature 0, fixed seed, one host | `plan.json` `runtime.references` (model only); host and settings P10 |
| GLM-5.3 | Z.AI, `chat`, reasoning `low`, temperature 0, seed 20261109 | `protocol.md` section 4.4; `plan.json` model only (P10) |
| Ragas, statsmodels | Ragas 0.4.3; statsmodels in the `stats` dependency group | Ragas: `uv.lock`. statsmodels: Missing: RDY task 15.6 adds a `stats` dependency group and pins the version |
| Query instruction | Empty string | Missing: P11 |
| Reranker instruction | llama-server default Qwen3-Reranker instruction, text recorded | Missing: P11 |
| Hybrid settings | RRF constant, per-side fusion depth, BM25 tokeniser and parameters | Missing: P11 |
| Search settings | Section 3 values | `protocol.md` section 0.3; `plan.json` `decision_rule` |
| FreshStack revision and corpus tree hash | Full 49,514-document corpus | Missing: P1 |
| Legal RAG Bench revision and SHA-256 | To record | Missing: C35 task 4A.4, RDY task 13.4 |
| FinanceBench, BioASQ revisions and hashes | Section 4 | `protocol.md` section 4.1 |
| `halves.json` SHA-256 | Seed 20261115, FinanceBench by document | Missing: P12 |
| Prompt template hashes | Answer, both closed-book, oracle, classifier | Missing: P13 |
| GPU type, image digest, driver, CUDA | Chosen by the `protocol.md` section 0.8a rule | Environment record per pod; GPU choice is a readiness task |
| Seeds | One seed per use (table below) | This file; `plan.json` `seed` holds 20261101 |
| Freeze commit and OSF link | At the freeze | `plan.json` `frozen` (empty today) |

**Seeds.** Each seed has one use, except 20261101. That seed has three independent uses: the answer model's hosted seed, the FinanceBench sign-flip test and the FreshStack and BioASQ permutation check. This is safe: the hosted seed goes to the provider and feeds no local random draw, and the two tests run on different datasets, so no draw feeds two results. The Ragas judge and classifier seeds are pins still to record (P10). New seeds wait for the user (P9).

| Seed | Use |
| --- | --- |
| 20261101 | Answer model hosted seed; FinanceBench sign-flip test (section 9 point 4); FreshStack and BioASQ permutation check (section 9 point 6) |
| 20261109 | GLM-5.3 hosted seed |
| 20261112 | Classifier-gate sample (100 smoke claims) |
| 20261113 | Correctness label sample: questions and answer setups (section 11.2) |
| 20261115 | Halves A and B (`halves.json`) |
| 20261116 | Faithfulness label sample (450 claims) |
| 20261117 | Reranker rank check (200 pairs per size) |
| 20261118 | MDE pilot questions (40 per core dataset, half A) |
| 20261119 | Length-controlled check (300 claims) |
| 20261120 | Optional relevance audit (O3) |
| 20261121 | Factorial smoke run and test pod: setups and 5 questions per dataset |
| 20261122 | L2 subset, claim kinds (30 of 100) |
| 20261123 | L2 subset, faithfulness (135 of 450) |
| 20261124 | L2 subset, correctness (60 of 200) |
| 20261125 | Faithfulness-gate kappa bootstrap (each checker, pooled and per dataset) |
| 20261126 | Differential-error rule bootstrap (GLM-5.3 specificity difference) |
| 20261127 | Correctness-gate kappa bootstrap |
| 20261128 | Correctness-gate AUC bootstrap |
| 20261129 | L1 against L2 kappa bootstrap |
| 20261130 | RAGFlow page-number gate sample (FinanceBench, half A) |
| 20261131 | RAGFlow repeatability sample (half A) |
| 20261132 | Part 2 label list order (both systems shuffled into one list) |
| 20261133 | Part 2 correctness-gate sample |
| 20261134 | Part 2 correctness-gate kappa bootstrap |
| 20261135 | Part 2 correctness-gate AUC bootstrap |

## 17. Budget, ceiling, stop rule and drop order

- **Estimate**: about **$730** on an RTX 4090 at $0.89 per hour (estimate). It is the A3 estimate of about $690 plus the full FreshStack corpus (reviewer estimate about 30 to 40 extra pod hours, about $30 to $40, not timed: P2), the second closed-book run (about $3 hosted and about 1 pod hour, by analogy with the first) and the pilot. The pilot cost is not yet estimated: it is projected from the P2 timing, added here before the freeze and approved by the user before the pod starts (section 10). Search cost barely changes with corpus size, because the rerank pool stays 100.
- **Ceiling**: **$975**, pods and hosted calls together (1.5 x the A2 estimate, about 1.34 x this one). At 3 times slower reranking than assumed, the total is about $950 (estimate), still under the ceiling with little margin. The OpenRouter key carries a credit limit equal to the hosted share of the ceiling, so an overrun ends as a clean `out_of_credit` stop.
- **Checks**: before the freeze (test pod extrapolation), on the build pods after the search stage, and at each stage end while the replicate pods run. Each projection uses billing and measured rates only, never scores.
- **Drop order at the ceiling** (results-blind, applied in order, each step recorded with the projection that triggered it): (1) Legal RAG Bench answer generation; (2) the length-controlled check; (3) the closed-book run with the RAG prompt; then stop. E1 is not in this order: it has its own ceiling (P16). No confirmatory item is dropped by choice. If the closed-book RAG-prompt run is dropped, the contamination sensitivity (section 13) uses the own-knowledge closed-book run alone, and the report says so.
- **Stop rule.** The run is complete when every search setup has its run, every answer setup and dataset has 3 runs, the closed-book, oracle and length-controlled runs are done, G1 to G3 are checked, and every Ragas and checker row is judged or counted. A run that finishes every confirmatory item after one or more drop steps is "complete with registered drops": each drop is a numbered deviation (section 20). A run is "incomplete" only when a confirmatory item is missing. The run stops early when the preflight fails, a gate fails, or a projection reaches the ceiling after the last drop step.
- **Part 2 and E1** each get their own estimate and ceiling before their runs (P16).

## 18. What Experiment 35 fixes for Part 2 and E1

Experiment 35 fixes the points below. On these points this section wins over the proposal. The proposal governs every other Part 2 and E1 fact until the Part 2 protocol is frozen; after that, the Part 2 protocol governs them (section 1).

- **OMRS setup**: the A3 cell (section 14.1), its hash time-stamped on OSF before half B is scored. Part 2 runs on half B only, once per system.
- **Estimand, fixed before any half-B score.** The cost decision at FLOW step 7.2a fixes which estimand applies. It is recorded before any half-B score exists, so the estimand is never chosen after seeing results.
  - If the matched RAGFlow search runs: C1 and C2 compare "selected OMRS against selected RAGFlow". The RAGFlow cell is chosen on half A by the same selection rule. Its configuration hash is time-stamped on OSF with the OMRS hash, before any half-B score exists. Default RAGFlow is then a secondary, descriptive row.
  - If the matched search does not run: C1 and C2 compare "selected OMRS against default RAGFlow".
  - In both cases the shared models are fixed.
- **Default RAGFlow** is one RAGFlow run: its defaults from the pinned release, plus the shared parts (the embedder, and the reranker when the A3 cell has it on) and the two measurement settings (cut-off 0, depth 100). When the matched search does not run, the RAGFlow side of the main row and of the defaults row is this same run, and the table shows its scores once.
- **Shared and fixed**: the chosen embedder; the reranker when the A3 cell has it on (same Qwen3-Reranker file and size, through RAGFlow's rerank setting); the answer model, prompt and 20,480-token budget; the checkers and judges; the corpus snapshot (FreshStack full corpus); the question IDs and halves.
- **Set for measurement in RAGFlow**: similarity cut-off 0, retrieval depth 100. Every other RAGFlow setting is its default, read from the pinned release, not from main-branch documentation (P16). The Part 2 protocol gives a settings table with three columns: shared and fixed, default kept, set for measurement.
- **Matched RAGFlow search** on half A (same selection rule, 12 to 24 cells, retrieval only) guards against a weak-baseline comparison (Armstrong et al. 2009; Lin 2019; Yang et al. 2019). Its exact cell list (the RAGFlow settings varied and their levels) is fixed and recorded before the cost measurement at FLOW step 7.2. It runs only if its projected pod cost, measured at FLOW step 7.2, is at most $50. The decision is recorded at FLOW step 7.2a, before any half-B score exists, and it fixes the estimand above.
- **Pre-freeze RAGFlow samples** (page-number gate, seed 20261130; repeatability check, seed 20261131) come from half A only.
- **FinanceBench unit**: page for every question and both systems; pre-freeze gate that RAGFlow returns page numbers; fallback to document for every question and both systems if it fails; the other unit as labelled sensitivity (`protocol.md` section 0.12 item 4).
- **C1 and C2**: one Holm family of 2 per core dataset, Legal exploratory. Each holds when it counts with the same sign on at least 2 core datasets; opposite signs are reported as a dataset-dependent effect, and it does not hold. The report states the direction. C1 is nDCG@10. C2 is continuous `AnswerCorrectness`; number match is secondary. Both use the analysis of section 9 (GEE on question clusters for FreshStack and BioASQ, document-level sign-flip on FinanceBench). No McNemar test where documents cluster (Obuchowski 1998). C2 needs its own Part 2 correctness gate (the section 11.2 rule, labels from both systems); a failed gate leaves C2 in the family as not testable.
- **Part 2 missing outcomes**: every half-B question stays in both systems' denominators. A RAGFlow timeout or error after the content-blind retry rule scores 0 for C1 and gets an answer from empty evidence for C2. A short list scores missing ranks as not relevant. A document RAGFlow fails to parse stays in the corpus count and is reported with the questions it affects. An unmappable chunk counts as not relevant and is counted. A sensitivity analysis uses the questions where both systems indexed every gold document.
- **Labels**: L2 is the primary Part 2 labeller; system identity is hidden; both systems' answers are shuffled into one list (seed 20261132). The Part 2 correctness-gate sample and its bootstraps use seeds 20261133 to 20261135.
- **Budget**: Part 2 gets its own estimate and ceiling (P16).

## 19. Release

| Artefact | Content | Licence or rule |
| --- | --- | --- |
| Code, harness, prompts, analysis scripts, label guidelines | As run, with commit | Repository licence |
| Ranked lists | Unit IDs per setup and question, TREC run format | Per dataset licence (IDs only) |
| Answers | Text per setup, run and question | FinanceBench CC BY-NC 4.0; FreshStack CC BY-SA 4.0; Legal CC BY-NC-SA 4.0; BioASQ CC BY 2.5 with the NLM currency notice |
| Cited evidence | Unit and chunk IDs, never text | As ranked lists |
| Verdicts, classifier rows, Ragas rows, scores | Per answer and claim | Per dataset licence |
| Human labels | L1, L2 and adjudicated, with guidelines | Per dataset licence |
| Run records, environment records, compute table, deviation log | As written | Repository licence |
| RAGFlow configurations, outputs, maintainer replies | Part 2 | Part 2 protocol |
| Not released | Corpus text, PDFs, derived text; LLM-AggreFact data (CC BY-ND, evaluation only) | |

- **Re-judge kit**: a script that rebuilds evidence text from the pinned dataset revisions and the released IDs, so faithfulness and correctness can be judged again with a newer model without redistributing corpus text.
- Archive on Zenodo with a DOI, one archive per dataset licence. Remove names and home-folder paths before release.

## 20. Deviation policy

After the freeze, every change is a dated, numbered deviation. The report lists each one with its reason, its time (before or after seeing the affected data) and its effect on each claim. Each is also added to `plan.json` `amendments` and uploaded to the OSF project. A run on another llama.cpp build needs a deviation first.

## 21. Reporting

- Decisions per row and per hypothesis, estimates with unadjusted 95% intervals, SESOI and MDE lines, and the gated rows marked "not testable".
- **Unjudged share** at 10 per setup and dataset, and condensed-list nDCG@10 (unjudged units removed; Sakai 2007) as a sensitivity for H1 to H5, where the qrels list judged non-relevant units (P4). For a dataset whose qrels hold positives only, the report states that neither can be computed.
- Realised chunk-length distribution per chunk-size level and dataset.
- Sensitivity tables: GEE against permutation disagreements; FinanceBench page rules; missing-outcome bounds; closed-book subset; length-controlled check; A3 cell under any-page credit.
- **Compute table**: GPU type, pod hours per stage including every pre-freeze pod (test pod, GPU timing, pilot, smoke runs), hosted tokens and cost per role, an energy estimate (GPU hours times board power; Strubell et al. 2019; Lacoste et al. 2019), `resent_calls`, error rows per stage and role, and every `out_of_credit` stop.
- Returned model ID and provider per hosted call, with the count of differences from the requested values.
- AI assistance: the plan was drafted with AI agents; the paper says so.

## 22. Limitations

- Scope S: one model family at Q8_0 on llama.cpp, English only, no query instruction, one dataset per domain, one hosted answer model behind an ID that may change.
- The reranker's default instruction is a web-search instruction, applied to finance and legal text.
- Incomplete relevance judgements: unjudged units count as not relevant (Zobel 1998; Buckley and Voorhees 2004). FreshStack qrels came from pools that included BM25 and fusion systems, which can favour hybrid search. The BioASQ mini corpus is built from gold passages of many questions, so a passage gold for another question is unlabelled here. Most FinanceBench questions have one gold page, while figures often repeat on other pages.
- BioASQ is split by question, so some gold passages are shared across halves.
- Chunk size is a cap, not the realised length; BioASQ and Legal chunks barely change with it.
- H8 faithfulness is checker-measured, and the checker sees longer passages at bigger chunks; the differential-error rule and the length-controlled check address this only in part.
- H8b is conditional on reranker on and hybrid on at the chosen sizes.
- The answer model may have seen benchmark text in training; the closed-book runs bound this only in part.
- One index build per cell.
- L1 is an OMRS author.

## 23. Open items before the freeze

**OPEN (the user decides):**

- O1. The OSF mechanism that time-stamps the A3 configuration hash (proposed: a file upload to the registered project).
- O2. The SESOI value, 0.02 nDCG@10.
- O3. Whether the optional blind relevance audit for H3 and C1 runs.
- O4. L2's name, role and relation to the project.
- O5. The ethics query to the university and its answer.
- O6. BioASQ rows 12 to 19 as sanity checks (BioASQ family 8, families 19 / 19 / 8, 46 contrasts), with H8a and H8b holding only on FinanceBench and FreshStack. This changes the earlier 2-of-3 rule for H8. The alternative: keep rows 12 to 19 in the BioASQ family (16 rows, 54 contrasts, alpha 0.05/16 for the BioASQ MDE) and keep 2-of-3 for H8a and H8b. The user confirms one before the freeze.

**Pre-freeze tasks:**

- P1. Download the full FreshStack LangChain corpus at a pinned revision (user approval at build time); record the revision, the row count and the tree hash.
- P2. Time one full-corpus FreshStack index build; update the estimate before relying on it.
- P3. Check whether FreshStack nugget labels allow alpha-nDCG@10 with the benchmark's scorer; pin the scorer or record "not available".
- P4. Check, per dataset, whether the qrels list judged non-relevant units.
- P5. Fix the pilot cell list (at most the four H7 corner indexes per core dataset), project the pilot cost from the P2 timing, get the user's approval, run the pilot, and fill the MDE table (or apply the registered fallback of section 10).
- P6. Name the smoke and test-pod answer files that feed the H8 MDE rows.
- P7. Restate the checker 2-point tolerance against the MDE table.
- P8. Write the label guidelines for each set, with worked examples outside every sample.
- P9. Confirm or change the new seeds 20261118, 20261119 and 20261121 to 20261135 (seeds table, section 16), and the length-controlled sample size (300). Seed 20261120 (audit) is used only if O3 is yes; confirm it then.
- P10. Record the tokenizer revision, answer-model host, reasoning mode, output cap and context length, and the judge, classifier and GLM-5.3 settings (the Ragas judge and classifier seeds included) in `plan.json`.
- P11. Record the query instruction, the reranker instruction text and the hybrid settings in `plan.json`.
- P12. Write `halves.json`; record its SHA-256; list every smoke and pre-freeze question ID with its half.
- P13. Record the prompt template hashes.
- P14. Set the `evidence_recall_20k` tolerance.
- P15. Check that no file still names `openai/gpt-6.1-terra` as a cross-check judge.
- P16. Part 2 and E1: own estimates and ceilings; RAGFlow defaults read from the pinned release; the settings table; the matched RAGFlow cell list (fixed before FLOW step 7.2), the cost measured at FLOW step 7.2 and the decision at FLOW step 7.2a, which also fixes the Part 2 estimand (section 18).

Existing readiness tasks also close before the freeze: reranker pins, GPU choice, classifier gate, Legal revision, answer-model context length, test pod session.

## 24. References

- Armstrong, Moffat, Webber and Zobel 2009, CIKM. doi:10.1145/1645953.1646031.
- Buckley and Voorhees 2004, "Retrieval evaluation with incomplete information", SIGIR. doi:10.1145/1008992.1009000.
- Byrt, Bishop and Carlin 1993, "Bias, prevalence and kappa", J. Clin. Epidemiol. doi:10.1016/0895-4356(93)90018-V.
- Carterette 2012, "Multiple testing in statistical analysis of systems-based information retrieval experiments", ACM TOIS. doi:10.1145/2094072.2094076.
- Cawley and Talbot 2010, "On over-fitting in model selection and subsequent selection bias in performance evaluation", JMLR 11. https://www.jmlr.org/papers/v11/cawley10a.html.
- Dodge et al. 2019, "Show your work: improved reporting of experimental results", EMNLP. arXiv 1909.03004; doi:10.18653/v1/D19-1224.
- Feinstein and Cicchetti 1990, "High agreement but low kappa", J. Clin. Epidemiol. doi:10.1016/0895-4356(90)90158-L.
- FinanceBench, Islam et al. 2023. arXiv 2311.11944.
- FreshStack, Thakur et al. 2025. arXiv 2504.13128.
- Lacoste et al. 2019, machine learning emissions. arXiv 1910.09700.
- Lakens 2017, "Equivalence tests", Soc. Psychol. Personal. Sci. doi:10.1177/1948550617697177.
- Liang and Zeger 1986, Biometrika. doi:10.1093/biomet/73.1.13.
- Lin 2019, "The neural hype and comparisons against weak baselines", SIGIR Forum. doi:10.1145/3308774.3308781.
- Liu et al. 2024, "Lost in the middle", TACL. doi:10.1162/tacl_a_00638.
- Mancl and DeRouen 2001, "A covariance estimator for GEE with improved small-sample properties", Biometrics. doi:10.1111/j.0006-341X.2001.00126.x.
- MiniCheck, Tang, Laban and Durrett 2024. arXiv 2404.10774.
- Miller 2024, "Adding error bars to evals". arXiv 2411.00640.
- Obuchowski 1998, "On the comparison of correlated proportions for clustered data", Stat. Med. 17(13), 1495.
- OSF Prereg form. https://preregr.opens.science/articles/form_OSFprereg_v1.html.
- Qwen3 Embedding, Zhang et al. 2025. arXiv 2506.05176.
- Ragas, Es et al. 2023. arXiv 2309.15217.
- Sakai 2007, "Alternatives to Bpref", SIGIR. doi:10.1145/1277741.1277756.
- Sim and Wright 2005, "The kappa statistic in reliability studies", Physical Therapy. doi:10.1093/ptj/85.3.257.
- Smucker, Allan and Carterette 2007, "A comparison of statistical significance tests for information retrieval evaluation", CIKM. doi:10.1145/1321440.1321528.
- Strubell et al. 2019, energy and policy considerations. arXiv 1906.02243.
- Urbano, Lima and Hanjalic 2019, "Statistical significance testing in information retrieval: an empirical analysis of type I, type II and type III errors", SIGIR. doi:10.1145/3331184.3331259; arXiv 1905.11096.
- Wang et al. 2024, "Searching for best practices in retrieval-augmented generation", EMNLP. doi:10.18653/v1/2024.emnlp-main.981.
- Yang, Lu, Yang and Lin 2019, "Critically examining the 'neural hype'", SIGIR. doi:10.1145/3331184.3331340.
- Zobel 1998, "How reliable are the results of large-scale information retrieval experiments?", SIGIR. doi:10.1145/290941.291014.
