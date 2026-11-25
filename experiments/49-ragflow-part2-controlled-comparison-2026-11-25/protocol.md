# Experiment 49: Part 2, OMRS against RAGFlow on half B (controlled comparison)

- **Folder**: `49-ragflow-part2-controlled-comparison-2026-11-25`
- **Record**: [experiment.json](experiment.json) holds category, size and status.
- **Operator**: Aizat
- **Related**: Experiment 35 (`35-full-rag-benchmark-2026-11-01`, Part 1; its `preregistration.md` section 18 wins on the points it fixes for Part 2), `docs/proposals/first-publication-benchmark.md` (Step 3), OpenSpec changes `rag-benchmark-readiness-flow` (group 7) and `exp35-main-run-readiness` (task 16.16)

## Status: DRAFT, 2026-11-25. Not frozen.

This is a draft for FLOW task 7.1. It holds every item that the list "What the Part 2 protocol must hold before its freeze" requires (proposal Step 3, 20 items; FLOW 7.1, items 1 to 16). A value that needs pod timing or an owner decision is a `TODO` with the task that closes it. No such value is invented here. Section 22 lists every TODO.

Part 2 is deposited on OSF at the Experiment 35 freeze (FLOW 7.3, G7), before any half-B score exists. After the freeze, the deviation policy of section 19 applies.

## 1. Question

With the shared models fixed, does the OMRS setup selected on half A differ from RAGFlow in retrieval quality (C1) and in answer correctness (C2), per core dataset, on held-out half-B questions?

The answer decides which comparison claim the paper may make about OMRS and RAGFlow, and in which direction.

## 2. Hypotheses and decision rule

"RAGFlow" below means selected RAGFlow if the matched search runs, else default RAGFlow (section 3).

- **C1 (primary)**: selected OMRS and RAGFlow differ in retrieval nDCG@10. Null: zero difference. Two-sided, per core dataset.
- **C2 (primary)**: selected OMRS and RAGFlow differ in answer correctness, measured by continuous Ragas `AnswerCorrectness`. Null: zero difference. Two-sided, per core dataset. FinanceBench number match is secondary.
- **Family**: C1 and C2 form their own Holm family, separate from H1 to H8b of Experiment 35. Holm runs per dataset across C1 and C2 (a family of 2 per core dataset). Core datasets are FinanceBench, FreshStack and BioASQ. Legal RAG Bench is exploratory and gets paired intervals and no confirmatory test.
- **Decision rule**: C1 (or C2) holds when it counts with the same sign on at least 2 of the 3 core datasets. A count with the opposite sign on the third dataset is reported as a dataset-dependent effect and does not stop the hypothesis holding. The report states the direction.
- **Tests** (pre-registration section 9): FreshStack and BioASQ use a GEE on question clusters with bias-reduced covariance (Mancl and DeRouen 2001) and a t reference distribution. FinanceBench uses the document-level sign-flip permutation test (100,000 draws, seed 20261101, interval by inverting the same test). No McNemar test. Any binary secondary measure is reported descriptively or with a test that allows for clustering.
- **C2 gate**: C2 needs its own Part 2 correctness gate (pre-registration section 11.2): Cohen's kappa point estimate at least 0.60 and lower 95% bound at least 0.40, per core dataset, on labels from both systems' answers, plus the AUC check on the continuous score. A failed gate leaves C2 in its family as "not testable" on that dataset. Every gate interval is a percentile bootstrap (10,000 resamples of questions) with its own seed (section 11).
- **No equivalence claim.** A non-significant result means no difference was detected at this sample size. The paper claims superiority only where the tests support it.
- **Minimum detectable effect (MDE)** for C1 and C2 per dataset, from half-A data only: `TODO(P20, Exp 35 task 4D.5 pilot)`. The pilot (40 seeded half-A questions per core dataset) needs the owner's approval and pod time. Registered fallback if the owner declines the pilot: assumed standard deviations, labelled assumed (pre-registration section 10). Half B holds about half of each dataset, so power is lower than in Part 1. C2 is expected to detect only large correctness differences.

## 3. Estimand and the matched-search decision

The decision at FLOW step 7.2a fixes the estimand before any half-B score exists. The estimand is never chosen after seeing results. The shared models are fixed in both cases. OMRS is the A3 cell chosen on half A from the 72-setup search of Experiment 35 (section 14.1 of its pre-registration).

| Decision at 7.2a | Estimand | RAGFlow side |
| --- | --- | --- |
| Matched search runs (projected pod cost at most $50) | "selected OMRS against selected RAGFlow" | RAGFlow cell chosen on half A by the same selection rule. Its configuration hash is time-stamped on OSF with the OMRS hash. Default RAGFlow becomes a secondary, descriptive row. |
| Matched search does not run | "selected OMRS against default RAGFlow" | One default RAGFlow run. The paper names the tuning gap wherever it states the C1 or C2 result. |

- **Decision, projected pod cost and date**: `TODO(FLOW 7.2a, after the 7.2 timing)`.
- **Estimand in force**: `TODO(FLOW 7.2a)`.

## 4. RAGFlow pin

Pin before the freeze (FLOW 7.2). Read every value from the pinned release. Never read main-branch documentation.

| Item | Value |
| --- | --- |
| RAGFlow release tag | `TODO(FLOW 7.2)` |
| Container digest: RAGFlow server | `TODO(FLOW 7.2)` |
| Container digest: search engine | `TODO(FLOW 7.2)` |
| Container digest: database | `TODO(FLOW 7.2)` |
| Container digest: object store | `TODO(FLOW 7.2)` |
| Container digest: cache | `TODO(FLOW 7.2)` |
| DeepDoc model versions | `TODO(FLOW 7.2)` |
| API version | `TODO(FLOW 7.2)` |

## 5. Settings table

Three columns, as the pre-registration (section 18) and the proposal (rule 1) require. The rows of the "shared and fixed" and "set for measurement" columns are fixed now. The "default kept" column is read from the pinned release at FLOW 7.2.

| Setting | Shared and fixed | Default kept | Set for measurement |
| --- | --- | --- | --- |
| Embedder | The embedder chosen on half A (`TODO(FLOW 7.4)`), same GGUF file as OMRS | | |
| Query instruction | Same as OMRS (empty string, Exp 35 `plan.json` `pins.settings.embedding.query_instruction`) | | |
| Reranker | When the A3 cell has it on: same Qwen3-Reranker file and size, through RAGFlow's rerank setting. Its instruction: same text as OMRS | | |
| Answer model, prompt, budget | `deepseek/deepseek-v4.1-flash-1017`, the Exp 35 answer prompt, 20,480-token budget, through the common OMRS answer harness (section 8) | | |
| Checkers and judges | Exp 35 checkers (GLM-5.3, Clef-Flash) and Ragas judge, same settings | | |
| Corpus snapshot | Full FreshStack corpus at the Exp 35 revision; the Exp 35 revisions of FinanceBench, BioASQ and Legal RAG Bench | | |
| Question IDs and halves | Exp 35 `halves.json` (SHA-256 in section 7) | | |
| Similarity cut-off | | | 0 |
| Retrieval depth | | | 100 |
| Chunk method and chunk size | | `TODO(FLOW 7.2)` | |
| Tokenizer | | `TODO(FLOW 7.2)` | |
| Parser and layout model | | `TODO(FLOW 7.2)` | |
| LLM-based parsing features (each one: off or stated) | | `TODO(FLOW 7.2)` | |
| Keyword and vector weights | | `TODO(FLOW 7.2)` | |
| Page size and page depth | | `TODO(FLOW 7.2)` | depth 100 |
| Any other setting | | `TODO(FLOW 7.2)`: read from the pinned release | |

Each system keeps its own parser, chunker and retrieval method. Those are what the comparison measures.

## 6. Model serving

- RAGFlow calls the same llama.cpp router, build and GGUF files (SHA-256 in `plan.json` `runtime.models`) as OMRS, through OpenAI-compatible endpoints.
- The run writes an environment record, as Part 1 does. `verify_llamacpp_runtime` runs before the first call and a mismatch stops the run.
- Run record and environment record rules are those of Experiment 35 (section 19 of this file).
- If a RAGFlow feature cannot use these models, the blocker is recorded and reported. No other model is substituted (FLOW 7.2).
- Connection details (endpoint names, ports, router preset): `TODO(FLOW 7.2)`.

## 7. Data, halves and pre-freeze samples

- **Questions**: half B only. No selection step in Part 1 or Part 2 reads half B.
- **Halves**: `halves.json` of Experiment 35, seed 20261115, SHA-256 `7ccff757d7c04e821d3383e2ead4eb1300e52ee7f579f620f4c35e4f13de1a26` (recorded 2026-11-25, RDY task 16.12; `plan.json` `pins.recorded.halves` of Experiment 35). FinanceBench is split by document. The other datasets are split by question.
- **Half-B sizes**: FinanceBench 76, FreshStack 101, BioASQ 353, Legal RAG Bench 50.
- **Corpus**: the full FreshStack corpus as in Part 1. The timing run per dataset indexes the corpus only and sends no question.
- **Each system runs once.** Search runs once per system. The core datasets are confirmatory. Legal RAG Bench is exploratory.
- **Pre-freeze samples**, from half A only:
  - Page-number gate: FinanceBench, seed 20261130, size `TODO(FLOW 7.2; owner)`.
  - Repeatability check: seed 20261131, size `TODO(FLOW 7.2; owner)`.
  - The matched RAGFlow search, if it runs, also reads half A only.
- **Already seen**: the pre-registration section 5 table of Experiment 35 lists the questions seen before the freeze. RAGFlow samples may not use a question listed there for a gate decision. `TODO(FLOW 7.2)`: confirm that no sampled question sits in that list.

## 8. Evidence mapping and the answer harness input

- **Unit mapping**: every retrieved chunk maps to the dataset's unit ID after the same collapse as Experiment 35: FinanceBench page, FreshStack document, BioASQ or Legal passage. The first occurrence of each unit is kept in rank order and the list is cut at 10 units. nDCG@10 is scored on those lists. Relevance is binary.
- **Retrieval depth**: 100 requested from RAGFlow.
- **FinanceBench relevance unit** (one unit, fixed before the run, for every FinanceBench question and both systems):
  - Primary unit: the page. A RAGFlow chunk counts for its first page. An OMRS stored chunk has one page.
  - Page gate (before the freeze): on a seeded half-A FinanceBench sample (section 7), every RAGFlow chunk must carry a page number. Result: `TODO(FLOW 7.2)`.
  - Fallback: if the gate fails, the primary unit is the document for every question and both systems. The page-level result becomes a labelled sensitivity analysis.
  - If the gate passes but a chunk in the main run has no page number, that chunk counts as not relevant at page level for its system. The report gives the count per system.
  - The other unit is a labelled sensitivity analysis. It is required only when both systems give page provenance. Otherwise the report says it is unavailable and gives the count of questions affected.
  - No question is dropped and no question changes unit because of one system's output.
- **Unmappable chunk**: a chunk that maps to no dataset unit counts as not relevant, keeps its rank and is counted per system.
- **Answer harness input**: each system's retrieved evidence goes through the common OMRS answer harness. The input format of a RAGFlow chunk is: text, title and order as returned by RAGFlow, one evidence item per chunk, in rank order. Each item carries its Qwen3 token count (pinned Qwen3 tokenizer, revision in Exp 35 `plan.json` `pins.settings.embedding`). Evidence is cut at 20,480 tokens in rank order. The crossing chunk is truncated and kept as its own item. The cut total and the realised token total are saved per question. Both systems use the same prompt and answer model. `TODO(FLOW 7.2)`: confirm on one sample that the RAGFlow chunk fields (text, title, order) are all present.
- **RAGFlow's own chat output** may be reported descriptively. It never enters C1 or C2.
- **Report**: one table per dataset, separate from the Experiment 35 tables. Mean context tokens per question for each system.

## 9. Determinism and the repeatability rule

- Search runs once per system.
- **RAGFlow repeatability check** (before the freeze): repeat RAGFlow retrieval on a small seeded half-A sample (section 7). Report whether the ranked lists match.
- **What a mismatch means for C1**: `TODO(owner)`. The proposal gives two options: report the mismatch and keep C1, or block C1 until the cause is known. The owner chooses before the freeze.
- **OMRS side**: rerun the OMRS search for the chosen setup on its sealed Experiment 35 index and check that the lists equal the saved ones.

## 10. Missing outcomes

Every half-B question stays in both systems' denominators. Retries follow the content-blind resend rule of Part 1 only.

| Case | C1 | C2 |
| --- | --- | --- |
| RAGFlow timeout or error that remains after the resend rule | Scores 0 | The answer model gets empty evidence |
| List shorter than 10 units | Missing ranks count as not relevant | Not applicable |
| Document RAGFlow fails to parse | Stays in the corpus count; reported with the questions it affects | Same |
| Chunk that maps to no unit | Counts as not relevant; counted | Same |
| Answer missing after the resend rule, from either system | Not applicable | Scores 0 for correctness |
| Ragas row not judged, for either system | Not applicable | The question leaves the C2 contrast (complete pairs). Every exclusion is counted per system |

- A sensitivity analysis for C1 uses the questions where both systems indexed every gold document.
- A sensitivity analysis for C2 scores unjudged rows 0 and keeps every question.
- The pre-registration section 12 rules apply to both systems alike.

## 11. Labels

- **L2** is the primary Part 2 labeller. L1 (the OMRS authors) is the check, not the gate. L2's name, role and relation to the project go in the run record before the first label, never in public files.
- **System identity is hidden.** Both systems' answers are shuffled into one list (seed 20261132).
- **Guideline**: one written Part 2 correctness guideline, with worked examples drawn from outside every sample. It is fixed before the first label and released (pre-registration section 11, P8). `TODO(Exp 35 task 16.8)`: the guideline file and its hash.
- **Correctness-gate sample**: seed 20261133. Kappa bootstrap seed 20261134. AUC bootstrap seed 20261135.
- **Counts** (sample size per dataset, number of labels for L1 and for L2): `TODO(P16; owner, with the O4 plan)`. L2 labels every Part 2 item in both plans (pre-registration O4).
- **Gate**: per core dataset, kappa point estimate at least 0.60, lower 95% bound at least 0.40, plus the AUC check on the continuous score. A statistic that is undefined fails closed (pre-registration section 11.2).
- The Experiment 35 label counts do not change.

## 12. Tuning budget and the matched RAGFlow search

- **Cell list**: the exact matched RAGFlow cell list (the RAGFlow settings varied and their levels, 12 to 24 cells, retrieval only) is fixed and recorded before the FLOW 7.2 cost measurement. `TODO(owner, before FLOW 7.2)`.
- **Cost measurement**: one corpus-only index per dataset at FLOW 7.2, with the GPU cost recorded. The projected pod cost of the search on half A follows from it. `TODO(FLOW 7.2)`.
- **Rule**: the search runs only if the projected pod cost is at most $50. The decision and its cost figure are recorded at FLOW 7.2a, before any half-B score exists.
- **Selection rule if it runs**: the A3 rule of Experiment 35 (pre-registration section 14.1), applied to the RAGFlow cells on half A.
- **Search-cost figure** (section 18).

## 13. Defaults row

- One RAGFlow run: defaults read from the pinned release, plus the shared parts (the embedder, and the reranker when the A3 cell has it on) and the two measurement settings (cut-off 0, depth 100).
- Beside it: OMRS shipped defaults, with the embedder chosen on half A and OMRS's own shipped retrieval settings. Both use the same answer model.
- When the matched search runs, the defaults row is a secondary, descriptive row. When it does not run, this same run is the RAGFlow side of the main row and the table shows its scores once.
- The row names the tuning gap. It gets paired confidence intervals and no confirmatory claim.

## 14. Budget

- **Part 2 estimate and ceiling**, and **E1 estimate and ceiling** (E1 is Step 4 of the proposal, descriptive): `TODO(FLOW 7.2a; owner)`. They need the 7.2 timing. They are recorded before the freeze.
- **Drop order at the Part 2 ceiling**: `TODO(owner)`. Drop order is fixed before any run and is results-blind, as in pre-registration section 17.
- E1 has its own ceiling and is dropped first when the project budget is short.
- Pods: quote the price first, and delete the pod when the copy is done.

## 15. Conflict of interest, rerun kit and maintainer log

- The authors built OMRS. The paper states this.
- Safeguards: the pre-registration and its deviation log; selection on half A only; Holm families fixed before the run; blind labels with L2 as primary labeller; the published RAGFlow settings table; the maintainer correspondence; release of every output, RAGFlow outputs included.
- **Rerun kit**: a kit that reruns both systems on half B (commands, pins, environment record). `TODO(FLOW 7.5 preparation; owner)`: folder and contents.
- **Maintainer log**: the RAGFlow configuration is sent to the RAGFlow maintainers before the run. Every reply is logged here. `TODO(FLOW 7.2)`: send date, channel and replies.

## 16. Release table

| Item | When | Where |
| --- | --- | --- |
| RAGFlow configurations (pinned settings table, section 5) | After half B is scored | `TODO(owner)` |
| RAGFlow outputs (ranked lists, answers, scores) | After half B is scored | `TODO(owner)` |
| Maintainer replies | With the paper | `TODO(owner)` |

The release table follows pre-registration section 19. `TODO(owner)`: confirm the places.

## 17. A3 configuration hash and the OSF time-stamp

- **Definition** (pre-registration section 14.1): the configuration hash is the SHA-256 of the canonical JSON (keys sorted, no spaces, no ASCII escaping) of the selected cell's resolved settings, plus the SHA-256 of `halves.json` as the top-level field `halves_sha256`.
- **Time-stamp**: a file upload to the registered OSF project time-stamps the hash before any half-B score is computed, for Experiment 35 or Part 2 (O1). `selection.json` and `osf-timestamp.json` record it. The user does the upload (FLOW 7.3 for the deposit, FLOW 7.4 for the time-stamp).
- If the matched search runs, the selected RAGFlow configuration hash is time-stamped with the OMRS hash.
- OSF project link and deposit commit hash: `TODO(FLOW 7.3, owner)`.

## 18. Search-cost figure

- **Estimator**: the expected maximum pooled half-A score over n setups drawn at random, adapted from Dodge et al. 2019 (drawn without replacement), computed exactly from the scores sorted in ascending order (pre-registration section 14.3). One curve covers the 12 A3 cells and one covers the 72 setups.
- RAGFlow has no point unless its matched search runs. Then it gets its own curve over its half-A cells.

## 19. Run record, environment record and deviation policy

- Run record and environment record rules are those of Experiment 35: each run appends one line to `output/run-records.jsonl` with the start time, git commit, dirty-tree flag, plan SHA-256 and the command. The environment record names the GPU, image digest, driver, CUDA version and llama.cpp build.
- After the freeze, a change is a dated, numbered deviation, added to the amendments list and uploaded to OSF (pre-registration section 20).
- `plan.json` `frozen` stays empty until the freeze.

## 20. Analysis

- **Stats level**: expert (as Experiment 35).
- **Seeds** (all from the Experiment 35 seeds table; each has one use): 20261115 halves, 20261130 page gate, 20261131 repeatability, 20261132 label order, 20261133 correctness sample, 20261134 kappa bootstrap, 20261135 AUC bootstrap. The answer model's hosted seed is 20261101, shared with Experiment 35.
- **Analysis scripts**: reuse the Experiment 35 scripts (`score35.py`, `join35.py`, `bootstrap35.py`, `correct35.py`) with a Part 2 plan. `TODO(owner)`: confirm whether Part 2 needs its own scripts, and where they live. No script is written in this draft.
- **Blind relevance audit**: no audit by default. It runs only if the mean unjudged share in the top 10 units differs by more than 5 percentage points between OMRS and RAGFlow on a core dataset whose qrels list judged non-relevant units (pre-registration O3).

## 21. Runtime

- **Purpose**: publication (`purpose` in `experiment.json`).
- **Runtime under test**: no.
- **Local models**: run through llama.cpp from public GGUF files. The `runtime` block of `plan.json` is copied from Experiment 35 and lists every candidate embedder, reranker and checker. `TODO(FLOW 7.4)`: narrow it to the embedder and reranker size that the A3 selection picks.
- **Hosted references**: copied from Experiment 35 `plan.json` `runtime.references` (answer model, Ragas judge and classifier, GLM-5.3).
- **Tolerance**: copied from Experiment 35 (0.005 absolute on nDCG@10, Recall@10, MRR@10 and hit@page).
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score. A mismatch stops the run.

## 22. TODO index

| Section | TODO | Closed by |
| --- | --- | --- |
| 2 | MDE for C1 and C2 per dataset | Exp 35 task 4D.5 (pilot, owner approval, pod time) |
| 3 | Matched-search decision, projected pod cost, date, estimand in force | FLOW 7.2a (needs 7.2 timing) |
| 4 | RAGFlow release tag, container digests, DeepDoc versions, API version | FLOW 7.2 |
| 5 | "Default kept" column; embedder after selection | FLOW 7.2; FLOW 7.4 |
| 6 | Connection details to the llama.cpp router | FLOW 7.2 |
| 7 | Page-gate and repeatability sample sizes; no overlap with seen questions | FLOW 7.2; owner |
| 8 | Page-gate result; check of RAGFlow chunk fields | FLOW 7.2 |
| 9 | What a repeatability mismatch means for C1 | Owner |
| 11 | Guideline hash; label counts and the O4 plan | Exp 35 task 16.8; owner (P16) |
| 12 | Matched RAGFlow cell list; cost measurement | Owner (before 7.2); FLOW 7.2 |
| 14 | Part 2 and E1 estimates and ceilings; Part 2 drop order | FLOW 7.2a; owner |
| 15 | Rerun kit; maintainer send date and replies | Owner; FLOW 7.2 |
| 16 | Release places | Owner |
| 17 | OSF link and deposit commit hash | FLOW 7.3 (owner) |
| 20 | Part 2 analysis scripts | Owner |
| 21 | Narrow `runtime` block to the selected models | FLOW 7.4 |
