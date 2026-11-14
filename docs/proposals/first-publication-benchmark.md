# First publication: a reproducible local RAG benchmark of OMRS

Draft 7, 14 November 2026 (Experiment 35 amendment A4 after the publication-grade methods review, findings F1 to F30, plus the fixes from the post-fix consistency review, findings C1 to C24 in protocol.md section 0.13: the new pre-registration governs every Experiment 35 design fact; Part 2 gets its estimand, shared reranker, missing-outcome and label rules, and a list of what its protocol must hold; limitations and references fixed). Draft 6, 13 November 2026 (proposal becomes the master plan; Part 1 aligned with Experiment 35 amendments A1–A3; RAGFlow as the single controlled competitor on held-out half B; haiku.rag dropped). Draft 5, 12 November 2026, added a controlled comparison and parked PipesHub for v4. Draft 4, 9 November 2026, added the EnterpriseRAG-Bench protocol. Plan only. No measured run has started.

This is the first paper of the fellowship programme. The manṭiq work in `v4` (authority-aware retrieval and reasoning gates) comes after it. This paper does not wait for that work.

## Master plan and source of truth

This proposal is the master plan for the first OMRS publication. It holds the scope, the order of work, what the paper claims and why, Part 2 and E1. Each experiment's governing file holds how its part runs: counts, seeds, models, statistical methods, gates and costs.

- Part 1 is Experiment 35. Its governing file is the pre-registration `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md` (amendment A4, 14 November 2026). It holds the live design only. `protocol.md` sections 0.1 to 0.13 (amendments A1 to A4) and sections 1 to 7 are history.
- Part 2 (controlled comparison with RAGFlow) gets its own protocol before the freeze, and E1 (EnterpriseRAG-Bench context run) gets one before its run. Pre-registration section 18 lists what Experiment 35 fixes for them.

Rule: for every Experiment 35 design fact, the pre-registration governs. Where this proposal and the pre-registration disagree on such a fact, the pre-registration wins and this proposal is corrected. For Part 2 and E1, pre-registration section 18 wins over this proposal on the points it fixes: the OMRS setup and its hash, the halves, the shared parts, the measurement settings, the C1 and C2 measures and tests, and the Part 2 missing-outcome rules. This proposal governs every other Part 2 and E1 fact until the Part 2 protocol is frozen. After that, the Part 2 protocol governs them. This proposal also governs scope and order of work. This file states Experiment 35 facts in short form and points to the pre-registration section. It does not copy long tables.

OSF deposit at the freeze: the pre-registration as the main file, with this proposal, the protocol history (`protocol.md`), `plan.json` and the Part 2 protocol.

Related records:

- `experiments/35-full-rag-benchmark-2026-11-01/preregistration.md`: Part 1 live design (governs).
- `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` and `plan.json`: Part 1 history and runtime pins.
- `openspec/changes/experiment-35-full-document-rag-benchmark/`: Part 1 design decisions and their sources.
- `openspec/changes/exp35-main-run-readiness/`: Part 1 harness code.
- `openspec/changes/rag-benchmark-readiness-flow/`: task order and gates for the whole benchmark.
- `openspec/changes/archive/2026-11-08-pipeline-sweep-llamacpp/`: Step 1.
- `openspec/changes/archive/2026-10-27-reproducible-experiment-runtime/carry-forward.md`: which past experiments go forward.
- ADR-103 (local models run through llama.cpp with a public GGUF file) and ADR-119 (Experiment 35 model matrix and claim checker).

## Summary

OMRS is a local-first, modular RAG framework. The paper reports one Confirmatory benchmark of the full pipeline on three public datasets from three domains: finance (FinanceBench), software (FreshStack, LangChain slice) and biomedicine (BioASQ). A fourth dataset, Legal RAG Bench, is exploratory.

Part 1 (Experiment 35) crosses four pipeline choices in a full factorial: embedder size, chunk size, reranker and hybrid search. It then measures how chunk size changes answer faithfulness and correctness. Part 2 runs RAGFlow, a widely used open-source RAG application, against one OMRS setup on held-out questions, with the shared models fixed. E1 runs OMRS on EnterpriseRAG-Bench as descriptive context beside its public leaderboard.

What runs where:

- Local: ingestion, chunking, embedding, indexing, reranking and search. Every model runs through a pinned llama.cpp GGUF build, so another group can rebuild each index and repeat each search on its own machine. The second claim checker, Clef-Flash, also runs locally.
- Hosted: answer generation, the main claim checker and the Ragas judge. Each is pinned by model ID, and every call records the returned model ID and provider.

One hosted answer model is used throughout. This is a stated limitation.

The paper answers three research questions:

- **RQ1 (absolute performance):** what retrieval and answer quality does OMRS reach on FinanceBench, FreshStack, BioASQ and (exploratory) Legal RAG Bench under stated models and settings? The headline is the A3-selected cell scored on half B (pre-registration section 14.3). The 72-setup table on all questions is descriptive.
- **RQ2 (component effects):** how do embedder size, chunk size, reranker size and hybrid search change retrieval quality? How does chunk size change answer faithfulness and correctness?
- **RQ3 (external comparison):** with the shared models fixed, how does the OMRS setup selected on half A compare on half B with RAGFlow (Part 2)? The step 7.2a decision fixes the RAGFlow side: RAGFlow selected on half A if the matched search runs, else RAGFlow at its defaults. Where does OMRS sit beside published systems on EnterpriseRAG-Bench (E1, descriptive)?

The claims stay testable. OMRS reaches stated scores under stated conditions. Named pipeline choices change those scores by measured amounts. Selected OMRS and RAGFlow (default, or selected on half A if the matched search runs) differ by measured amounts only where the paired tests support it. Every claim holds only within scope S (pre-registration section 2): Qwen3-Embedding and Qwen3-Reranker at Q8_0 on one pinned llama.cpp build, English text, no query instruction, the reranker's default instruction, one hosted answer model, and the datasets as built.

## Why now

- Past experiments (1 to 42) were optimisation runs. Many used Ollama, small question sets (for example 17 queries) or remain unfinished. They cannot be cited as they are.
- ADR-103 gives a reproducible runtime, and the checker enforces the `publication` purpose.
- A systems paper with honest, pinned results fits the fellowship period. It also gives the manṭiq papers a tested base.

## Order and gates

1. Freeze Part 1. The operator approves the pre-registration, `plan.json` and the run budget (master flow gate G7). The open items O1 to O6 and the pre-freeze tasks P1 to P16 (pre-registration section 23) close first. The Part 2 protocol exists before this point (it is not written yet).
2. Deposit on OSF in one deposit: the pre-registration as main file, this proposal, the protocol history, `plan.json` and the Part 2 protocol (C1, C2). Record the link and the commit hash.
3. Build and seal the 9 indexes per dataset. The rebuild gate G2 passes before any search writes output. Then run the 72 search setups on all questions (pre-registration section 14.2).
4. Score half A only. Apply the A3 rule. Write `selection.json`.
5. Time-stamp the A3 configuration hash by a file upload to the registered OSF project (open item O1: the user confirms the mechanism).
6. Only then score half B and start the answer stage. "Sealed" means the indexes only: half-B ranked lists exist on disk before step 5, but no half-B score is computed before it.
7. Run Part 2 on half B, once per system.
8. Run E1 if the budget allows. E1 is the first item to drop when the budget is short.

After the freeze, every change is a dated, numbered deviation. The report lists each one with its reason, its time (before or after seeing the affected data) and its effect on each claim. Each deviation also goes into `plan.json` `amendments` and is uploaded to the OSF project (pre-registration section 20). Part 2 follows the same policy.

The master flow `openspec/changes/rag-benchmark-readiness-flow` holds group 7 for Part 2 and E1.

## Step 1: pipeline sweep (done)

Done and archived on 8 November 2026 (Experiment 48, `openspec/changes/archive/2026-11-08-pipeline-sweep-llamacpp/`). It checked that every pipeline stage runs on the llama.cpp router and timed the embedders. Its findings fed the Experiment 35 plan.

## Step 2: Part 1, Experiment 35 (Confirmatory)

The pre-registration is the authority for every design fact and number in this part. This section is a short guide to it.

| Dataset | Domain | Questions | Gold unit | Licence | Status |
|---|---|---|---|---|---|
| FinanceBench (open sample) | Finance, real PDFs | 150 | Page | CC BY-NC 4.0 | Confirmatory |
| FreshStack, LangChain slice (full public corpus, 49,514 documents) | Software | 203 | Document | CC BY-SA 4.0 | Confirmatory |
| BioASQ (`enelpol/rag-mini-bioasq`, test split) | Biomedicine | 707 | Passage | CC BY 2.5 | Confirmatory |
| Legal RAG Bench (`isaacus/legal-rag-bench`) | Law | 100 | Passage | CC BY-NC-SA 4.0 | Exploratory |

BioASQ passed every data check, so the NFCorpus fallback is retired. RepoProbe moves to a later paper because it has no retrieval labels. No open medical dataset has real PDFs with page-level gold evidence, so FinanceBench is the only PDF dataset. EnterpriseRAG-Bench is not part of Experiment 35 (see E1).

- FreshStack: all 9 indexes are built on the full public LangChain corpus at a pinned revision. The 10,000-document subset of Experiments 9a and 22 (every gold document plus random distractors) is retired. No FreshStack result is compared with the public leaderboard unless the same corpus and metric are used. alpha-nDCG@10 is a secondary metric if the nugget labels allow it (pre-registration sections 4 and 6).
- Halves: seed 20261115. FinanceBench is split by document, so no document sits in both halves. The other datasets are split by question (pre-registration section 4).
- Existing data: earlier looks at these datasets (Experiments 9a, 10 and 22, smoke runs, the pilot) are declared in pre-registration section 5.

### Search stage: full factorial, no baseline

| Factor | Levels |
|---|---|
| Embedder | Qwen3-Embedding 0.6B, 4B, 8B |
| Chunk size | 512, 1,024, 2,048 Qwen3 tokens, 15% overlap |
| Reranker | Off, Qwen3-Reranker 0.6B, 4B, 8B |
| Hybrid search | Off, or BM25 plus dense |

Every combination runs on every dataset. No setup is the baseline: each hypothesis is a planned contrast across the grid. Chunk size replaces the old token-aware chunking arm. The ONNX MiniLM reranker is gone; every reranker runs on llama.cpp.

The primary metric is nDCG@10 at unit level, with the trec_eval formulas written in pre-registration section 6. Each setup saves its top 100 chunks. The chunks collapse to documents, pages or passages in rank order, and the list is cut at 10 units. Without this, bigger chunks would score higher only because each one covers more units. On FinanceBench a chunk counts for its first page. The H6 FinanceBench endpoint `evidence_recall_20k` gives a chunk credit for every gold page it overlaps (any-page credit); first-page credit is a sensitivity analysis.

### Answer stage

The answer stage uses the embedder and reranker size chosen on half A (pre-registration section 14.1). It has 15 setups, each run 3 times on all 1,160 questions: 12 crossed setups (chunk size x reranker on or off x hybrid on or off, 10 chunks of evidence each) and 3 token-matched setups (`c512-t20k`, `c1024-t20k`, `c2048-t20k`, reranker and hybrid on, evidence cut at 20,480 Qwen3 tokens). Two closed-book runs (own-knowledge prompt, and the RAG prompt with an empty evidence block) and an oracle run (gold evidence given directly) frame the results (pre-registration section 13).

- Faithfulness: claim checks. GLM-5.3 is the main checker; Clef-Flash (local) is the second.
- Correctness: Ragas `AnswerCorrectness` with `openai/gpt-oss-120b` as judge, plus a number match on FinanceBench. There is no cross-check judge: `openai/gpt-6.1-terra` is removed, because no cost estimate includes it.
- Human check: two labellers score samples blind (L1 750 labels, L2 225). Each checker must pass a faithfulness gate, and the correctness judge must pass a gate on each core dataset: kappa point estimate at least 0.60 and lower 95% bound at least 0.40. A row whose measure fails its gate stays in its Holm family as "not testable". Every gate interval is a percentile bootstrap (10,000 resamples by question). A differential-error rule makes H8a and H8b faithfulness exploratory if GLM-5.3 specificity differs between 512 and 2,048 chunks in either direction. If Clef-Flash fails its gate, its results are reported as not validated and change no confirmatory row (pre-registration section 11).
- Other Ragas metrics are secondary. Ragas is not the main faithfulness measure.

### Hypotheses H1 to H8b

Full wording, contrast rows and "holds" rules: pre-registration sections 7 and 8. Each null is a zero effect. Each hypothesis holds only within scope S.

- **H1:** a bigger embedder ranks gold units higher.
- **H2:** the reranker raises nDCG@10.
- **H3:** hybrid search raises nDCG@10.
- **H4:** reranker plus hybrid beats each alone (simple effects, not an interaction test).
- **H5:** a bigger reranker ranks better.
- **H6:** chunk size changes retrieval (the same row, same sign, on FinanceBench and FreshStack).
- **H7:** a bigger embedder gains more from bigger chunks (FinanceBench and FreshStack; expected to be underpowered).
- **H8a:** chunk size changes faithfulness and correctness in the crossed setups, where context length grows with chunk size (the same row, same sign, on FinanceBench and FreshStack; open item O6).
- **H8b:** chunk size changes faithfulness and correctness when evidence is held at 20,480 tokens. The paper says "chunk size itself changes X" only when H8b holds for X.

### Methods in short

Detail for each item is in the pre-registration section named.

- Search runs once per setup on a sealed index, and each index is built once. A rebuild check and a repeat check confirm determinism (section 15). Answer setups repeat to measure drift in the hosted API.
- Analysis: no mixed model. One clustered method gives every estimate, interval and p-value: GEE with bias-reduced covariance on question clusters for FreshStack, BioASQ and Legal, and a document-level sign-flip permutation test on FinanceBench (section 9).
- Holm families are fixed now: 19 contrasts on FinanceBench, 19 on FreshStack, 8 on BioASQ (46 in all; BioASQ rows 9 to 19 are sanity checks, open item O6); Legal is exploratory. No gate changes a family size (section 8). H1 to H5 hold on at least 2 of 3 core datasets. H6, H7, H8a and H8b hold only on FinanceBench and FreshStack. A two-sided hypothesis holds only when the same row counts with the same sign on every dataset its rule needs (section 7).
- Missing outcomes: every question stays in its denominator, with a rule per outcome (section 12).
- Power: a retrieval-only pilot on 40 seeded half-A questions per core dataset fills the minimum detectable effect table before the freeze. It builds at most the four H7 corner indexes per core dataset and does not reuse them. Its cost is projected from the P2 timing and approved before the pod starts; if the user declines, the table is filled from assumed SDs and labelled so. The smallest effect of interest is 0.02 nDCG@10 (open item O2). No equivalence claim is made (section 10).
- Every main-run pod uses one RunPod GPU type, chosen by a timing job before the freeze. The Mac scores the results.
- Budget: estimate about $730 (an estimate, not measured), ceiling $975, pods and hosted calls together. The hosted-call key carries a credit limit, so an overrun stops cleanly. At the ceiling a results-blind drop order applies: (1) Legal RAG Bench answer generation, (2) the length-controlled check, (3) the closed-book run with the RAG prompt, then stop. E1 has its own ceiling and is not in this order. A run that finishes every confirmatory item after drops is "complete with registered drops", each drop a numbered deviation. No confirmatory item is dropped by choice (section 17).
- Pre-registration: the pre-registration is the main file of the OSF deposit at the freeze commit, with this proposal, the protocol history, `plan.json` and the Part 2 protocol.

### Runtime and hosted models

- Local models: llama.cpp only. `plan.json` pins the repository, file, SHA-256, build and server arguments of each one. The live-server check passes before the first score. Pre-registration section 16 holds one pins table; the items still marked missing there (answer-model host, reasoning mode and output cap, query instruction, hybrid settings, FreshStack revision, prompt hashes) are pre-freeze tasks.
- Answer model: `deepseek/deepseek-v4.1-flash-1017`, through the API only, with one pinned upstream host. The open-weight model is too large for one pod, and smaller open models answer worse (protocol A2).
- Main claim checker GLM-5.3 and Ragas judge `openai/gpt-oss-120b`: hosted, pinned by model ID.
- Limitation: results describe OMRS retrieval with one hosted answer model. Clef-Flash gives a local path for the faithfulness check. The answer step has no local path in this paper.

## Step 3: Part 2, controlled comparison with RAGFlow (Confirmatory)

A separate experiment with its own number and protocol, deposited at the Experiment 35 freeze. It reuses the Experiment 35 corpora (FreshStack full corpus), question IDs, half split, prompt, answer model, checkers and judges. The points Experiment 35 fixes for Part 2 are in pre-registration section 18, which wins over this section on those points. This proposal governs every other Part 2 fact until the Part 2 protocol is frozen; after that, the Part 2 protocol governs them.

**Estimand.** The cost decision at master flow step 7.2a (rule 9) fixes which estimand applies, before any half-B score exists. The estimand is never chosen after seeing results. The shared models are fixed in both cases. OMRS is the A3 cell chosen on half A from the 72-setup search.

- If the matched RAGFlow search runs: "selected OMRS against selected RAGFlow". The RAGFlow cell is chosen on half A by the same selection rule. Its configuration hash is time-stamped on OSF with the OMRS hash, before any half-B score exists. Default RAGFlow becomes a secondary, descriptive row.
- If the matched search does not run: "selected OMRS against default RAGFlow". RAGFlow runs at its defaults, except the settings shared or set for measurement below. The paper names this tuning gap wherever it states the C1 or C2 result.

### Why RAGFlow alone

RAGFlow is the only controlled competitor. It has wide adoption and an Apache-2.0 licence. It accepts our llama.cpp models through OpenAI-compatible endpoints, and it returns the chunks it retrieved, so gold-label metrics apply. haiku.rag is dropped: its adoption is low, and one competitor cuts cost and the number of tests. For the wider field, the E1 context table lists the 39 systems on the EnterpriseRAG-Bench leaderboard.

Systems left out, and why:

- PipesHub (#1 on the leaderboard, entered by its own team). It runs an agent loop with several model calls per question and needs four extra databases. It moves to the v4 comparison, where agentic retrieval is in scope. When it runs, report its tokens and latency per question beside its score.
- GraphRAG and LightRAG. Building them needs a language model to read every document.
- Hosted-only and closed commercial systems. We cannot fix their models, and nobody can repeat the run.
- LlamaIndex and LangChain on default settings. These are libraries, not complete applications, and a default build would be a weak opponent.

### Which OMRS setup

The main comparison uses one OMRS setup chosen on half A of the Experiment 35 split. A pre-registered rule fixes all four factors: embedder, chunk size, reranker level and hybrid. The exact rule is pre-registration section 14.1 (amendment A3, as restated by A4). It runs in two steps. First, pooled over the three core datasets on half A, it picks the embedder and the reranker size (the Experiment 35 selection rule, amended). Then, at that embedder and reranker size, it picks chunk size, reranker on or off and hybrid on or off by the pooled mean nDCG@10 on half A. Its principles:

- Choose on the three core datasets pooled. Legal RAG Bench takes no part in selection.
- Setups within 0.01 of the best tie. Ties go to the cheaper setup in this order: reranker off, hybrid off, lowest index cost, then smaller chunk size. Index cost is the number of stored vector values (chunks times embedding dimension) summed over the three core datasets, known before any score.
- The configuration hash is the SHA-256 of the canonical JSON of the selected cell's resolved settings plus the SHA-256 of `halves.json`. A file upload to the registered OSF project time-stamps it before any half-B score is computed (open item O1).

A **defaults row** sits beside the main comparison: OMRS shipped defaults against default RAGFlow. Both use the embedder chosen on half A and the same answer model. OMRS keeps its own shipped retrieval settings. Default RAGFlow is one RAGFlow run: its defaults read from the pinned release, plus the shared parts (the embedder, and the reranker when the A3 cell has it on) and the two measurement settings (cut-off 0, depth 100) of rule 1. When the matched search does not run, the RAGFlow side of the main row and of the defaults row is this same run, and the table shows its scores once. The row names the tuning gap, which is the part of any OMRS lead that comes from choosing a setup on half A. The defaults row is secondary. It gets paired confidence intervals and no confirmatory claim.

A **search-cost figure** shows how much of the OMRS score comes from selection over the grid. It plots the expected maximum pooled half-A score over n setups drawn at random, adapted from Dodge et al. 2019 (drawn without replacement), computed exactly from the scores sorted in ascending order. One curve covers the 12 A3 cells and one covers the 72 setups. RAGFlow has no point unless its matched search runs; then it gets its own curve over its half-A cells (pre-registration section 14.3).

### Which questions

Half B only. No selection step in Part 1 or Part 2 reads half B. Every pre-freeze RAGFlow sample (the page-number gate and the repeatability check) comes from half A only, and so does the matched RAGFlow search if it runs. The timing run per dataset indexes the corpus only and sends no question. Each system runs once. The three core datasets are confirmatory; Legal RAG Bench is exploratory. Half B is about half of each dataset, so power is lower than in Part 1. C2 is expected to detect only large correctness differences (pre-registration section 10). The Part 2 protocol states a minimum detectable effect for C1 and C2 per dataset before the freeze, and the report gives it again from the data.

### Rules that keep the comparison fair

1. **Shared parts are fixed.** Both systems use the embedder chosen on half A, the same answer model and prompt, the same 20,480-token budget, the same checkers and judges, the same corpus snapshot and the same question IDs and halves. When the A3 cell has the reranker on, RAGFlow gets the same Qwen3-Reranker file and size through its rerank setting. RAGFlow's similarity cut-off is set to 0 and its retrieval depth to 100, for measurement only. Every other RAGFlow setting is its default, read from the pinned release and not from main-branch documentation (a pre-freeze task). Each system keeps its own parser, chunker and retrieval method. Those are what the comparison measures. The Part 2 protocol gives a settings table with three columns: shared and fixed, default kept, set for measurement.
2. **Equal evidence.** Request retrieval depth 100 from RAGFlow. Score nDCG@10 on the same units as Experiment 35, after the same collapse. Both systems answer from evidence cut to the same 20,480-token budget. Report mean context tokens per question for each system. On FinanceBench the relevance unit is the one fixed in rule 3.
3. **FinanceBench relevance unit.** One unit, fixed before the run, applies to every FinanceBench question and to both systems. The primary unit is the page, as in Part 1 (a chunk counts for its first page). Pre-freeze gate: on a seeded FinanceBench sample from half A, confirm that RAGFlow returns a page number for each chunk. Pre-registered fallback: if the gate fails, the primary unit becomes the document for every question and both systems. If the gate passes but a chunk in the main run has no page number, that chunk counts as not relevant at page level for its system, and the report gives the count of such chunks per system. The other unit is reported as a labelled sensitivity analysis. It is required only when both systems provide page provenance; otherwise the report states it is unavailable and gives the count of questions affected. No question is dropped, and no question changes unit, because of one system's output.
4. **Answers.** Each system's retrieved evidence goes through the common OMRS answer harness, with the same prompt, the answer model `deepseek/deepseek-v4.1-flash-1017` and the same 20,480-token budget. The answer difference then comes from parsing, chunking and retrieval only. RAGFlow's own chat pipeline output may be reported descriptively, and it never enters C1 or C2.
5. **Determinism.** Search runs once per system. Before the run, repeat RAGFlow retrieval on a small seeded half-A sample and report whether the ranked lists match. Rerun OMRS search for the chosen setup on its sealed Experiment 35 index and check that the lists equal the saved ones.
6. **Pin and disclose.** Pin the RAGFlow release and container digests. Record the full configuration, parser settings included. Send the configuration to the RAGFlow maintainers before the run and log every reply. Do not tune RAGFlow below its defaults, apart from the settings of rule 1.
7. **Human labels.** Part 2 adds its own correctness labels and human-agreement sample, drawn from the answers of both systems, so judge agreement covers RAGFlow answers. L2 is the primary Part 2 labeller, so the OMRS authors' labels are the check, not the gate. System identity is hidden: both systems' answers are shuffled into one list. Labellers follow a written Part 2 correctness guideline, with worked examples from outside every sample, fixed before the first label. They run in Part 2. The Experiment 35 label counts do not change.
8. **Report.** Map every retrieved chunk to the dataset's unit ID. Give one table per dataset, separate from the Experiment 35 tables.
9. **Matched RAGFlow search (conditional).** A retrieval-only RAGFlow search on half A (the same selection rule, 12 to 24 cells). Its exact cell list (the RAGFlow settings varied and their levels) is fixed and recorded before the cost measurement at master flow step 7.2. It runs only if its projected pod cost, measured at master flow step 7.2, is at most $50. The decision and its cost figure are recorded at master flow step 7.2a, before any half-B score exists. The decision fixes the estimand (see "Estimand" above). If the search runs, the selected RAGFlow cell enters C1 and C2, its configuration hash is time-stamped on OSF with the OMRS hash before any half-B score exists, default RAGFlow becomes a secondary, descriptive row, and the search-cost figure shows a RAGFlow curve.
10. **Missing outcomes.** Every half-B question stays in both systems' denominators. Retries follow the content-blind resend rule of Part 1 only. A RAGFlow timeout or error that remains scores 0 for C1 and gets an answer from empty evidence for C2. A list shorter than 10 units scores the missing ranks as not relevant. A document RAGFlow fails to parse stays in the corpus count and is reported with the questions it affects. A chunk that does not map to a dataset unit counts as not relevant and is counted. A sensitivity analysis uses the questions where both systems indexed every gold document.
11. **Conflict of interest.** The authors built OMRS. The paper states this. The safeguards are: the pre-registration and its deviation log; selection on half A only; Holm families fixed before the run; blind labels with L2 as primary labeller; the published RAGFlow settings table and maintainer correspondence; and release of every output, RAGFlow outputs included.

### Hypotheses C1 and C2

"RAGFlow" below means selected RAGFlow if the matched search runs, else default RAGFlow (see "Estimand").

- **C1:** selected OMRS and RAGFlow differ in retrieval nDCG@10. Null: zero difference. Two-sided, per core dataset.
- **C2:** selected OMRS and RAGFlow differ in answer correctness, measured by continuous Ragas `AnswerCorrectness`. Null: zero difference. Two-sided, per core dataset. FinanceBench number match is secondary.

C1 and C2 form their own Holm family, separate from H1 to H8b: Holm runs per dataset across C1 and C2 (a family of 2 per core dataset). The cross-dataset rule is the 2-of-3 rule of Part 1 with the same-sign rule: a hypothesis holds when it counts with the same sign on at least 2 of the 3 core datasets (FinanceBench, FreshStack, BioASQ). Opposite signs are reported as a dataset-dependent effect, and the hypothesis does not hold. The report states the direction. Each test pairs the two systems question by question, with the analysis of pre-registration section 9:

- FreshStack and BioASQ: GEE on question clusters with bias-reduced covariance (Mancl and DeRouen 2001) and a t reference distribution.
- FinanceBench: questions share documents, so the decision p-value comes from a document-level sign-flip permutation test, and the interval inverts the same test. The randomisation test is the recommended test for comparing two IR systems (Smucker, Allan and Carterette 2007); here it flips signs per document, not per question.
- No McNemar test where documents cluster. Any binary secondary measure is reported descriptively or with a test that allows for clustering (Obuchowski 1998).

C2 needs its own Part 2 correctness gate: the pre-registration section 11.2 rule (kappa point estimate at least 0.60 and lower 95% bound at least 0.40, per core dataset), on labels from both systems' answers. A failed gate leaves C2 in the family as "not testable" on that dataset. Legal RAG Bench and the defaults row get paired intervals and no confirmatory test.

The paper claims superiority only where the tests support it. No TOST margin is planned, so the paper makes no equivalence claim. A non-significant result means no difference was detected at this sample size.

What this comparison can claim: with the shared models fixed, the measured difference between the OMRS setup selected on half A and RAGFlow (at its defaults, or selected on half A by the same rule if the matched search runs), on held-out questions. Without the matched search it does not show that OMRS beats a tuned RAGFlow. Han et al. 2025 (RAG against GraphRAG) fixed the answer model, chunk size, embedding model and retrieval budget in the same way. BERGEN and FlashRAG fix shared parts inside one toolkit. The half split answers the selection-bias risk (Cawley and Talbot 2010). The shared reranker, the settings table, the defaults row, the search-cost figure and the maintainer review answer the weak-baseline risk (Armstrong et al. 2009; Yang et al. 2019; Lin 2019; Dodge et al. 2019). Holm within each dataset answers the multiple-testing risk of many-contrast IR experiments (Carterette 2012). The choice of tests draws on Urbano, Lima and Hanjalic 2019.

### Pre-registration

The Part 2 protocol (C1, C2) goes to OSF in the same deposit as the Experiment 35 pre-registration, at the freeze, before any half-B score exists. The A3 configuration hash is time-stamped on OSF before any half-B score is computed. After the freeze, Part 2 follows the deviation policy of pre-registration section 20.

### What the Part 2 protocol must hold before its freeze

Until these items exist, Part 2 cannot freeze. Each can be short in the protocol. They come from the methods review of 13 November 2026 (findings F2, F9, F10, F17 to F21, F27 to F29).

1. Experiment number, folder and `experiment.json` (purpose `publication`, Confirmatory), from master flow step 7.1.
2. C1 and C2 with nulls, decision rule, Holm family of 2 per core dataset and the 2-of-3 same-sign rule, as above.
3. RAGFlow pin: release tag, container digest of every service (RAGFlow, search engine, database, object store, cache), DeepDoc model versions and API version.
4. Settings table for both systems, three columns (shared and fixed, default kept, set for measurement). Rows cover chunk method and size, tokenizer, parser and layout model, every LLM-based parsing feature (off or stated), embedder, query instruction, reranker and its instruction, keyword and vector weights, similarity cut-off, search depth, page size and depth 100. Defaults are read from the pinned release.
5. Tuning budget and estimand: the exact matched RAGFlow cell list (settings varied and their levels), fixed before the master flow step 7.2 cost measurement; the matched-search decision at master flow step 7.2a (rule 9), with its cost figure measured at step 7.2, recorded before any half-B score. The decision fixes the estimand: "selected OMRS against selected RAGFlow" if the search runs (the RAGFlow configuration hash time-stamped on OSF with the OMRS hash), else "selected OMRS against default RAGFlow".
6. Model serving: RAGFlow calls the same llama.cpp router, build and GGUF files as OMRS, with an environment record and the live-server check before the first call.
7. Evidence mapping: chunk to unit ID per dataset, the FinanceBench page rule, page gate and fallback, and the unmappable-chunk rule.
8. Answer harness input: how a RAGFlow chunk becomes an evidence item (text, title, order), Qwen3 token counting for the 20,480-token budget, and truncation records.
9. Pre-freeze samples from half A only, with their seeds.
10. Repeatability check rule, and what a mismatch means for C1 (report and keep, or block).
11. Missing-outcome rules as rule 10, every half-B question kept in both denominators.
12. Labels: counts, seeds, guidelines, hidden system identity, L1 and L2 roles (L2 primary), and the per-dataset correctness gate.
13. Defaults row: definition (one RAGFlow run as pre-registration section 18) and secondary role; it is a descriptive row when the matched search runs, and shown once when it does not.
14. Budget: Part 2 estimate and ceiling, and the drop order at the ceiling.
15. Conflict-of-interest statement and safeguards (rule 11), a rerun kit for both systems on half B, and the maintainer correspondence log.
16. Release table for RAGFlow configurations, outputs and maintainer replies.
17. The A3 configuration hash definition and the OSF time-stamp before half B is scored.
18. The search-cost figure estimator, with the RAGFlow curve if the matched search runs.
19. Run record and environment record rules, as in Part 1, and the deviation policy.
20. The minimum detectable effect for C1 and C2 per dataset, from half-A data only.

## Step 4: EnterpriseRAG-Bench context run (E1, descriptive)

**E1:** OMRS's document recall, answer correctness, completeness and overall score on EnterpriseRAG-Bench, shown beside published systems. E1 is descriptive only. It has no significance test.

- Run the A3 setup once on the full corpus (511,962 synthetic documents). A subset would not be comparable with the leaderboard.
- Rerun the benchmark's published BM25 and vector-search baselines in our pipeline as a calibration anchor. If the reruns land near the published baseline scores, our pipeline and scoring match theirs.
- The benchmark uses GPT-5.4 as answer model and judge. Leaderboard entries mostly do not state their answer model. Each difference therefore compares whole configurations, not OMRS retrieval alone.
- E1 answer model: GPT-5.4, the same as the EnterpriseRAG-Bench baselines, because E1 only sits beside the leaderboard as context. All E1 runs in our pipeline (the A3 setup and the two baseline reruns) use GPT-5.4. This differs from Parts 1 and 2, which use `deepseek/deepseek-v4.1-flash-1017`.
- Put leaderboard scores in a separate context table. Give each score its label revision, the date checked and the answer model where stated.
- Cost: E1 needs its own estimate and ceiling before any E1 run. E1 stays descriptive and is dropped first if the budget is short.

Evaluation procedure:

1. Pin the benchmark commit and the corpus revision. Record the gold-label revision for each score.
2. Use the main `questions.jsonl`. Exclude the metadata-dependent `extra_questions.jsonl`. Check the scored-question count: the paper describes 500 questions; the leaderboard categories summed to 470 on 9 November 2026.
3. Save one JSONL row per question: `{"question_id":"qst_0001","answer":"...","document_ids":["dsid_abc","dsid_def"]}`. Map each retrieved chunk to its `dsid_*` identifier and remove duplicates.
4. Run the official `src.scripts.answer_evaluation.metrics_based_eval` with GPT-5.4 and record every argument.
5. Keep the default citation stripping and document-correction flow. Do not use `--skip-citation-stripping` or `--no-correction`. Keep `questions_updated.jsonl` and report the corrected questions.
6. Use `--limit` and `--resume` only for harness checks and resumed runs. A limited run is not a leaderboard result.
7. Confirm the judging and submission procedure with Onyx before the run. For a leaderboard entry, give Onyx the OMRS commit, frozen configuration, model identities, corpus revision, commands and saved outputs.

## Publication rules

Sources: Taylor & Francis "streamlining how we describe research outputs", and the Edinburgh Napier open access guide and policy (v3.0).

Article type: Software Tool Article. It must give:

- the reason the tool was built;
- details of the code;
- example input data;
- example output, and how to read it.

The alternative is a Research Article. F1000Research is in the Napier Taylor & Francis deal. Ask repository@napier.ac.uk to confirm that the deal covers a Software Tool Article.

Before submission:

1. Confirm that the journal is in a Napier deal. Check it in DOAJ and with Think. Check. Submit.
2. Tell co-authors that the Napier open access policy applies to them.

At submission:

3. Be the corresponding author with the Napier affiliation and Napier email.
4. Add the rights retention sentence to the funding acknowledgement and the cover letter: "For the purpose of open access, the author has applied a Creative Commons Attribution (CC BY) 4.0 license to any Author Accepted Manuscript version arising from this submission."

On acceptance:

5. Deposit the accepted manuscript in Worktribe within 3 months.
6. Put the data and code DOI (Zenodo) in Worktribe.

After publication:

7. Record the dataset and the code in Worktribe as their own outputs, linked to the paper.

The journal's own author guide covers ORCID, CRediT, the funding wording, conflicts of interest, AI-tool disclosure and preprints. The Napier pages do not.

## What the publication rules change in the experiment

1. Build a small example set that we may share, with its expected output and a short guide to reading it. The Software Tool Article needs it.
2. Separate shareable outputs from restricted ones in `output/`.
3. Respect the dataset licences:
   - FinanceBench is CC BY-NC. Do not release its text or derived files under CC BY.
   - FreshStack is CC BY-SA. Release derived files under CC BY-SA.
   - BioASQ is CC BY 2.5, released with the NLM terms notice.
   - Legal RAG Bench is CC BY-NC-SA 4.0. Do not release its text or derived files under CC BY. Release derived files under CC BY-NC-SA.
   - EnterpriseRAG-Bench is MIT.
   - Do not publish the corpus text.
   - Release each artefact under its rule in the release table of pre-registration section 19: code and label guidelines, ranked lists, answers, cited evidence IDs (never text), verdicts and scores, human labels, run and environment records, the compute table and the deviation log. RAGFlow configurations, outputs and maintainer replies follow the Part 2 protocol.
   - Ship a re-judge kit: a script that rebuilds evidence text from the pinned dataset revisions and the released IDs, so a newer model can judge the answers again without redistributing corpus text.
4. Archive code and outputs on Zenodo with a DOI. Keep each dataset's derived files in their own archive with their own licence.
5. Before the repository or a release goes public, remove names and home-folder paths.
6. Report compute in one table (pre-registration section 21): GPU type, pod hours per stage including every pre-freeze pod (test pod, GPU timing, pilot, smoke runs), hosted tokens and cost per role, an energy estimate (GPU hours times board power), `resent_calls`, error rows per stage and role, and every `out_of_credit` stop (Strubell et al. 2019; Lacoste et al. 2019). Part 2 and E1 add their own rows.
7. State the conflict of interest (the authors built OMRS) and the AI assistance used to draft the plan.

## Risks

| Risk | Response |
|---|---|
| A small difference between llama.cpp back ends | Every main-run pod uses one GPU type. The plan states a tolerance per metric (ADR-103). |
| A checker or the correctness judge disagrees with people | Human labels gate each one before its scores count. A row whose measure fails its gate stays in its Holm family and is reported as "not testable". |
| The run costs more than planned | At the $975 ceiling the results-blind drop order of pre-registration section 17 applies: Legal RAG Bench answer generation, then the length-controlled check, then the closed-book run with the RAG prompt, then stop. A run with every confirmatory item done is "complete with registered drops". No confirmatory item is dropped by choice. Part 2 and E1 get their own estimate and ceiling before their runs; across the project, E1 is dropped first when the budget is short. |
| The reranker result changes on llama.cpp | Report it as found. A negative result is still a result. |
| Choosing the OMRS setup inflates its score | Choose on half A by a pre-registered rule, test on half B only, and publish the search-cost figure. |
| Half B is too small to detect a difference | Report the minimum detectable effect from the data. Make no equivalence claim. |
| The single hosted answer model changes behind its ID | Pin one upstream host. Record the returned model ID and provider per call. State it as a limitation. |
| RAGFlow cannot use our models, or hides its retrieved chunks | Record the blocker and report it. Do not substitute another model. |
| RAGFlow chunks carry no page number | The pre-freeze gate checks this on a half-A FinanceBench sample. If it fails, the primary unit is the document for every question and both systems. The page-level result is reported as a labelled sensitivity analysis, or as unavailable (with the count) when a system gives no page provenance. No question is dropped. |
| RAGFlow indexing costs too much GPU time | Time one RAGFlow index per dataset before the freeze (corpus only, no question). Report the cost. The matched RAGFlow search runs only if its projected pod cost is at most $50. |
| A reviewer says we set up RAGFlow badly | Share the reranker, set cut-off 0 and depth 100, read every other default from the pinned release, publish the three-column settings table, send it to the maintainers, report the defaults row and state the estimand fixed at master flow step 7.2a ("selected OMRS against default RAGFlow", or "against selected RAGFlow" if the matched search runs). |
| A RAGFlow call fails or a document fails to parse | Rule 10: the question stays in both denominators and the failure is scored and counted, with a sensitivity analysis on questions both systems indexed fully. |
| The authors' labels favour OMRS | L2 is the primary Part 2 labeller and system identity is hidden. The paper states the conflict of interest. |
| E1 indexing exceeds the budget | E1 is dropped first. Report the measured cost. |
| Public leaderboard results lack per-question scores | E1 is descriptive. Do not infer significance from rank or aggregate scores. |
| The journal deal does not cover the article type | Ask the library before writing. Research Article is the fallback. |

## Limitations and claim scope

The Experiment 35 limitations are in pre-registration section 22. The paper repeats them, and adds the Part 2 and E1 ones.

- Scope S: one model family at Q8_0 on one llama.cpp build, English only, no query instruction, one dataset per domain, and one hosted answer model that may change behind its ID. No claim extends past scope S.
- The reranker's default instruction is a web-search instruction, applied to finance and legal text.
- Unjudged units count as not relevant. FreshStack labels came from pools that included BM25 and fusion systems, which can favour hybrid search and keyword-weighted RAGFlow. Neither Part 2 system added to any pool.
- H8a and H8b faithfulness is checker-measured, and the checker sees longer passages for bigger chunks. The differential-error rule and the length-controlled check address this only in part. H8b holds only at reranker on and hybrid on with the chosen sizes.
- The answer model may have seen benchmark text in training. The closed-book runs bound this only in part.
- One index build per cell. H7 and C2 are expected to be underpowered.
- L1 is an OMRS author. If the matched RAGFlow search does not run (step 7.2a decision), Part 2 compares selected OMRS with RAGFlow at its defaults, so it does not show that OMRS beats a tuned RAGFlow. If it runs, Part 2 compares selected OMRS with RAGFlow selected on half A over its matched cells only.
- E1 compares whole configurations with a different answer model (GPT-5.4), so it says nothing about OMRS retrieval alone.

## Next steps

1. Done: pipeline sweep (Step 1), archived 8 November 2026.
2. Done: `pdf-inspector-page-provenance` (page numbers from the default reader).
3. Done: Experiment 35 amendments A1, A2 and A2c.
4. Ask the Napier library to confirm the article type and the deal.
5. Done: Experiment 35 amendment A3 (protocol section 0.12) holds the selection rule for Part 2.
6. Done: amendment A4 (protocol section 0.13) and the pre-registration, after the methods review of 13 November 2026.
7. Close the open items O1 to O6 and the pre-freeze tasks P1 to P16 of pre-registration section 23.
8. Reserve an experiment number for Part 2. Write its protocol, covering every item of "What the Part 2 protocol must hold before its freeze".
9. Before the freeze, pin the RAGFlow release and container digests and connect it to the llama.cpp models. Read the RAGFlow defaults from the pinned release. Time one index per dataset (corpus only). Measure the projected pod cost of the matched search at master flow step 7.2 and record the decision at step 7.2a; it fixes the Part 2 estimand. Check page provenance on a seeded half-A FinanceBench sample (the rule 3 gate: if RAGFlow returns no page for a chunk, the primary unit falls back to the document for both systems) and retrieval repeatability on half A. Send the settings table to the RAGFlow maintainers.
10. Write the Part 2 estimate and ceiling, and the E1 estimate and ceiling (pre-freeze task P16; no figure exists yet).
11. Done: group 7 (Part 2 and E1) is in `rag-benchmark-readiness-flow`. It must take the Part 2 requirements above.
12. Freeze Part 1. Deposit the pre-registration (main file), this proposal, the protocol history, `plan.json` and the Part 2 protocol on OSF together.
13. Before any E1 run, pin the corpus and leaderboard revisions. Confirm the GPT-5.4 judging or submission procedure with Onyx.

## Sources checked on 27 October, 9, 12, 13 and 14 November 2026

The Experiment 35 reference list is in pre-registration section 24.

- FinanceBench, arXiv 2311.11944.
- FreshStack, arXiv 2504.13128.
- MedRAG and MIRAGE, arXiv 2402.13178.
- BEIR, arXiv 2104.08663.
- Ragas, arXiv 2309.15217. Version 0.4.3 on PyPI is dated 13 January 2026.
- Miller 2024, "Adding Error Bars to Evals", arXiv 2411.00640.
- Smucker, Allan and Carterette 2007, "A comparison of statistical significance tests for information retrieval evaluation", CIKM, doi:10.1145/1321440.1321528 (randomisation test for two-system comparisons).
- Urbano, Lima and Hanjalic 2019, "Statistical significance testing in information retrieval: an empirical analysis of type I, type II and type III errors", SIGIR, doi:10.1145/3331184.3331259; arXiv 1905.11096.
- Carterette 2012, "Multiple testing in statistical analysis of systems-based information retrieval experiments", ACM TOIS, doi:10.1145/2094072.2094076.
- Cawley and Talbot 2010, "On over-fitting in model selection and subsequent selection bias in performance evaluation", JMLR 11, <https://www.jmlr.org/papers/v11/cawley10a.html>.
- Yang, Lu, Yang and Lin 2019, "Critically examining the 'neural hype'", SIGIR, doi:10.1145/3331184.3331340.
- Armstrong, Moffat, Webber and Zobel 2009, "Improvements that don't add up", CIKM, doi:10.1145/1645953.1646031.
- Lin 2019, "The neural hype and comparisons against weak baselines", SIGIR Forum, doi:10.1145/3308774.3308781.
- Dodge et al. 2019, "Show your work: improved reporting of experimental results", EMNLP, arXiv 1909.03004; doi:10.18653/v1/D19-1224 (expected validation performance).
- Mancl and DeRouen 2001, "A covariance estimator for GEE with improved small-sample properties", Biometrics, doi:10.1111/j.0006-341X.2001.00126.x.
- Obuchowski 1998, "On the comparison of correlated proportions for clustered data", Stat. Med. 17(13), 1495.
- OSF Prereg form, <https://preregr.opens.science/articles/form_OSFprereg_v1.html>.
- Strubell et al. 2019, energy and policy considerations, arXiv 1906.02243. Lacoste et al. 2019, machine learning emissions, arXiv 1910.09700.
- RAGPerf, arXiv 2603.10765.
- BERGEN, arXiv 2407.01102.
- FlashRAG, arXiv 2405.13576 and doi:10.1145/3701716.3715313.
- TREC 2024 RAG Track, arXiv 2411.09607.
- Hugging Face cards: `enelpol/rag-mini-bioasq`, `PatronusAI/financebench`, `freshstack/corpus-oct-2024`, `isaacus/legal-rag-bench`, `onyx-dot-app/EnterpriseRAG-Bench`.
- EnterpriseRAG-Bench, arXiv 2605.05253, `github.com/onyx-dot-app/EnterpriseRAG-Bench`, its Hugging Face leaderboard, `quickstart.md`, `methodology.md` and `src/scripts/answer_evaluation/metrics_based_eval.py` (checked 9 November 2026).
- EnterpriseRAG-Bench leaderboard, checked 12 November 2026 (last updated 3 November 2026, 39 systems): PipesHub #1 at 93.24, RAGFlow #26 at 50.24. Onyx does not list itself.
- RAGFlow, `github.com/infiniflow/ragflow` (Apache-2.0).
- Han et al. 2025, "RAG vs. GraphRAG: a systematic evaluation", arXiv 2502.11371.
- LightRAG, arXiv 2410.05779. RAGLAB, doi:10.18653/v1/2024.emnlp-demo.43.
- Taylor & Francis: <https://editorresources.taylorandfrancis.com/welcome-to-tf/policies-guidelines/streamlining-how-we-describe-research-outputs/>.
- Edinburgh Napier: <https://libguides.napier.ac.uk/c.php?g=685910&p=5352291>, the linked open access policy pages, and Open Access Policy v3.0.
