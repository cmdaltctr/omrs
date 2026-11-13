# First publication: a reproducible local RAG benchmark of OMRS

Draft 6, 13 November 2026 (proposal becomes the master plan; Part 1 aligned with Experiment 35 amendments A1–A3; RAGFlow as the single controlled competitor on held-out half B; haiku.rag dropped). Draft 5, 12 November 2026, added a controlled comparison and parked PipesHub for v4. Draft 4, 9 November 2026, added the EnterpriseRAG-Bench protocol. Plan only. No measured run has started.

This is the first paper of the fellowship programme. The manṭiq work in `v4` (authority-aware retrieval and reasoning gates) comes after it. This paper does not wait for that work.

## Master plan and source of truth

This proposal is the master plan for the first OMRS publication. It holds what the paper claims and why. Each experiment protocol holds how its part runs: counts, seeds, models, statistical models, gates and costs.

- Part 1 is Experiment 35. Its protocol is `experiments/35-full-rag-benchmark-2026-11-01/protocol.md`. Section 0 (amendments A1, A2, A2c and A3) is the current design.
- Part 2 (controlled comparison with RAGFlow) gets its own protocol before the freeze, and E1 (EnterpriseRAG-Bench context run) gets one before its run. Until then, this proposal is their only record.

Rule: where this proposal and a protocol disagree, this proposal wins. Fix the protocol with a dated amendment (A3 is the first). Do not copy protocol numbers into this file. This file names datasets, factors and factor levels only, so the two cannot drift.

Related records:

- `experiments/35-full-rag-benchmark-2026-11-01/protocol.md` and `plan.json`: Part 1 design and runtime pins.
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

- **RQ1 (absolute performance):** what retrieval and answer quality does OMRS reach on FinanceBench, FreshStack, BioASQ and (exploratory) Legal RAG Bench under stated models and settings?
- **RQ2 (component effects):** how do embedder size, chunk size, reranker size and hybrid search, and their interactions, change retrieval quality? How does chunk size change answer faithfulness and correctness?
- **RQ3 (external comparison):** with the shared models fixed, how does an OMRS setup chosen on half A compare with RAGFlow on half B (Part 2)? Where does OMRS sit beside published systems on EnterpriseRAG-Bench (E1, descriptive)?

The claims stay testable. OMRS reaches stated scores under stated conditions. Named pipeline choices change those scores by measured amounts. OMRS and RAGFlow differ by measured amounts only where the paired tests support it.

## Why now

- Past experiments (1 to 42) were optimisation runs. Many used Ollama, small question sets (for example 17 queries) or remain unfinished. They cannot be cited as they are.
- ADR-103 gives a reproducible runtime, and the checker enforces the `publication` purpose.
- A systems paper with honest, pinned results fits the fellowship period. It also gives the manṭiq papers a tested base.

## Order and gates

1. Freeze Part 1. The operator approves the Experiment 35 protocol, `plan.json` and the run budget (master flow gate G7). Amendment A3 and the Part 2 protocol exist before this point (A3 is written; the Part 2 protocol is not).
2. Deposit on OSF in one deposit: the Experiment 35 protocol and plan, the Part 2 protocol (C1, C2) and amendment A3. Record the link and the commit hash.
3. Run Experiment 35 as its protocol states.
4. Apply the A3 rule on half A as soon as the search stage is scored. Freeze the chosen OMRS setup. Record its configuration hash on OSF before anyone opens half B for Part 2.
5. Run Part 2 on half B, once per system.
6. Run E1 if the budget allows. E1 is the first item to drop when the budget is short.

The master flow `openspec/changes/rag-benchmark-readiness-flow` holds group 7 for Part 2 and E1.

## Step 1: pipeline sweep (done)

Done and archived on 8 November 2026 (Experiment 48, `openspec/changes/archive/2026-11-08-pipeline-sweep-llamacpp/`). It checked that every pipeline stage runs on the llama.cpp router and timed the embedders. Its findings fed the Experiment 35 plan.

## Step 2: Part 1, Experiment 35 (Confirmatory)

The protocol is the authority for every number in this part. Read section 0 first; it wins over the older sections of that file.

| Dataset | Domain | Questions | Gold unit | Licence | Status |
|---|---|---|---|---|---|
| FinanceBench (open sample) | Finance, real PDFs | 150 | Document and page | CC BY-NC 4.0 | Confirmatory |
| FreshStack, LangChain slice | Software | 203 | Document | CC BY-SA 4.0 | Confirmatory |
| BioASQ (`enelpol/rag-mini-bioasq`, test split) | Biomedicine | 707 | Passage | CC BY 2.5 | Confirmatory |
| Legal RAG Bench (`isaacus/legal-rag-bench`) | Law | 100 | Passage | CC BY-NC-SA 4.0 | Exploratory |

BioASQ passed every data check, so the NFCorpus fallback is retired. RepoProbe moves to a later paper because it has no retrieval labels. No open medical dataset has real PDFs with page-level gold evidence, so FinanceBench is the only PDF dataset. EnterpriseRAG-Bench is not part of Experiment 35 (see E1).

### Search stage: full factorial, no baseline

| Factor | Levels |
|---|---|
| Embedder | Qwen3-Embedding 0.6B, 4B, 8B |
| Chunk size | 512, 1,024, 2,048 Qwen3 tokens, 15% overlap |
| Reranker | Off, Qwen3-Reranker 0.6B, 4B, 8B |
| Hybrid search | Off, or BM25 plus dense |

Every combination runs on every dataset. No setup is the baseline: each hypothesis is a planned contrast across the grid. Chunk size replaces the old token-aware chunking arm. The ONNX MiniLM reranker is gone; every reranker runs on llama.cpp.

The primary metric is nDCG@10 at unit level. Each setup saves its top 100 chunks. The chunks collapse to documents, pages or passages in rank order, and the list is cut at 10 units. Without this, bigger chunks would score higher only because each one covers more units.

### Answer stage

The answer stage varies chunk size, reranker on or off and hybrid on or off. The embedder and reranker size are chosen on half A by the protocol's selection rule. Token-matched setups, one per chunk size (`c512-t20k`, `c1024-t20k`, `c2048-t20k`), hold the evidence at one token budget. A closed-book run (no retrieval) and an oracle run (gold evidence given directly) frame the results.

- Faithfulness: claim checks. GLM-5.3 is the main checker; Clef-Flash (local) is the second.
- Correctness: Ragas `AnswerCorrectness` with `openai/gpt-oss-120b` as judge, plus a number match on FinanceBench.
- Human check: two labellers score samples blind. Each checker and the correctness judge must pass its agreement gate before its scores count.
- Other Ragas metrics are secondary. Ragas is not the main faithfulness measure.

### Hypotheses H1 to H8

Full wording, contrasts and decision rules: protocol section 0.4, restated by A2 (section 0.10) and A2c (section 0.11).

- **H1:** a bigger embedder finds better evidence.
- **H2:** the reranker helps.
- **H3:** hybrid search helps.
- **H4:** reranker plus hybrid beats either alone.
- **H5:** a bigger reranker ranks better.
- **H6:** chunk size changes search quality (FinanceBench and FreshStack).
- **H7:** bigger embedders gain more from bigger chunks.
- **H8:** chunk size changes answer faithfulness and correctness.

### Methods in short

Detail for each item is in protocol sections 0.3 to 0.11.

- Search runs once per setup on a sealed index. A rebuild check and a repeat check confirm determinism. Answer setups repeat to measure drift in the hosted API.
- Each dataset gets one model of per-question scores with planned contrasts. P-values use cluster-robust errors, clustered by document on FinanceBench. Holm correction runs across the contrasts of each dataset. Cross-dataset rules decide when a hypothesis holds overall.
- Minimum detectable effects come from pilot data before the freeze. No equivalence claim is made.
- Every main-run pod uses one RunPod GPU type, chosen by a timing job before the freeze. The Mac scores the results.
- The budget has an estimate and a hard ceiling. The hosted-call key carries a credit limit, so an overrun stops cleanly.
- Pre-registration: the protocol and `plan.json` go to OSF at the freeze commit, with Part 2 and A3.

### Runtime and hosted models

- Local models: llama.cpp only. `plan.json` pins the repository, file, SHA-256, build and server arguments of each one. The live-server check passes before the first score.
- Answer model: `deepseek/deepseek-v4.1-flash-1017`, through the API only, with one pinned upstream host. The open-weight model is too large for one pod, and smaller open models answer worse (protocol A2).
- Main claim checker GLM-5.3 and Ragas judge `openai/gpt-oss-120b`: hosted, pinned by model ID.
- Limitation: results describe OMRS retrieval with one hosted answer model. Clef-Flash gives a local path for the faithfulness check. The answer step has no local path in this paper.

## Step 3: Part 2, controlled comparison with RAGFlow (Confirmatory)

A separate experiment with its own number and protocol, deposited at the Experiment 35 freeze. It reuses the Experiment 35 corpora, question IDs, half split, prompt, answer model, checkers and judges.

### Why RAGFlow alone

RAGFlow is the only controlled competitor. It has wide adoption and an Apache-2.0 licence. It accepts our llama.cpp models through OpenAI-compatible endpoints, and it returns the chunks it retrieved, so gold-label metrics apply. haiku.rag is dropped: its adoption is low, and one competitor cuts cost and the number of tests. For the wider field, the E1 context table lists the 39 systems on the EnterpriseRAG-Bench leaderboard.

Systems left out, and why:

- PipesHub (#1 on the leaderboard, entered by its own team). It runs an agent loop with several model calls per question and needs four extra databases. It moves to the v4 comparison, where agentic retrieval is in scope. When it runs, report its tokens and latency per question beside its score.
- GraphRAG and LightRAG. Building them needs a language model to read every document.
- Hosted-only and closed commercial systems. We cannot fix their models, and nobody can repeat the run.
- LlamaIndex and LangChain on default settings. These are libraries, not complete applications, and a default build would be a weak opponent.

### Which OMRS setup

The main comparison uses one OMRS setup chosen on half A of the Experiment 35 split. A pre-registered rule fixes all four factors: embedder, chunk size, reranker level and hybrid. The exact rule is Experiment 35 protocol amendment A3 (section 0.12, 13 November 2026). It runs in two steps. First, pooled over the three core datasets on half A, it picks the embedder and the reranker size (the Experiment 35 selection rule, amended). Then, at that embedder and reranker size, it picks chunk size, reranker on or off and hybrid on or off by the pooled mean nDCG@10 on half A. Its principles:

- Choose on the three core datasets pooled. Legal RAG Bench takes no part in selection.
- Setups within 0.01 of the best tie. Ties go to the cheaper setup in this order: reranker off, hybrid off, lowest index cost, then smaller chunk size.
- Record the configuration hash on OSF before half B is opened for Part 2.

A **defaults row** sits beside the main comparison: OMRS shipped defaults against RAGFlow documented defaults. Both use the embedder chosen on half A and the same answer model. Each keeps its own shipped retrieval settings. It names the tuning gap, which is the part of any OMRS lead that comes from choosing a setup on half A. The defaults row is secondary. It gets paired confidence intervals and no confirmatory claim. RAGFlow runs at its documented defaults in both rows.

A **search-cost figure** plots the best half-A score against the number of setups tried (expected validation performance). It shows how much of the OMRS score comes from selection over the grid.

### Which questions

Half B only. No selection step in Part 1 or Part 2 reads half B. Each system runs once. The three core datasets are confirmatory; Legal RAG Bench is exploratory. Half B is about half of each dataset, so power is lower than in Part 1. Report the minimum detectable effect computed from the data for each dataset and hypothesis.

### Rules that keep the comparison fair

1. **Shared parts are fixed.** Both systems use the embedder chosen on half A, the same answer model and prompt, the same checkers and judges, the same corpus snapshot and the same question IDs. Each system keeps its own parser, chunker and retrieval method. Those are what the comparison measures.
2. **Equal evidence.** Request retrieval depth 100 from RAGFlow. Score nDCG@10 on the same units as Experiment 35, after the same collapse. Both systems answer from evidence cut to the same 20,480-token budget. Report mean context tokens per question for each system. On FinanceBench the relevance unit is the one fixed in rule 3.
3. **FinanceBench relevance unit.** One unit, fixed before the run, applies to every FinanceBench question and to both systems. The primary unit is the page, as in Part 1 (a chunk counts for its first page). Pre-freeze gate: on a seeded FinanceBench sample, confirm that RAGFlow returns a page number for each chunk. Pre-registered fallback: if the gate fails, the primary unit becomes the document for every question and both systems. The other unit is reported as a labelled sensitivity analysis. No question is dropped, and no question changes unit, because of one system's output.
4. **Answers.** Each system's retrieved evidence goes through the common OMRS answer harness, with the same prompt, the answer model `deepseek/deepseek-v4.1-flash-1017` and the same 20,480-token budget. The answer difference then comes from parsing, chunking and retrieval only. RAGFlow's own chat pipeline output may be reported descriptively, and it never enters C1 or C2.
5. **Determinism.** Search runs once per system. Before the run, repeat RAGFlow retrieval on a small seeded sample and report whether the ranked lists match. Rerun OMRS search for the chosen setup on its sealed Experiment 35 index and check that the lists equal the saved ones.
6. **Pin and disclose.** Pin the RAGFlow release and container digest. Record the full configuration, parser settings included. Send the configuration to the RAGFlow maintainers before the run and log every reply. Use RAGFlow's documented defaults for every setting that is not shared. Do not tune it below them.
7. **Human labels.** Part 2 adds its own correctness labels and human-agreement sample, drawn from the answers of both systems, so checker and judge agreement covers RAGFlow answers. They run in Part 2. The Experiment 35 label counts do not change.
8. **Report.** Map every retrieved chunk to the dataset's unit ID. Give one table per dataset, separate from the Experiment 35 tables.

### Hypotheses C1 and C2

- **C1:** OMRS and RAGFlow differ in retrieval nDCG@10. Two-sided, per core dataset.
- **C2:** OMRS and RAGFlow differ in answer correctness. Two-sided, per core dataset.

C1 and C2 form their own Holm family, separate from H1 to H8: Holm runs per dataset across C1 and C2 (two tests per dataset). The cross-dataset rule is the one of Part 1: a hypothesis holds when it holds on at least 2 of the 3 core datasets (FinanceBench, FreshStack, BioASQ). Each test pairs the two systems question by question:

- Continuous metrics: paired permutation test, with a paired bootstrap 95% interval.
- Binary correctness: McNemar's exact test, or another exact paired test.
- FinanceBench: questions share documents, so p-values come from GEE with errors clustered by document, as in the protocol.

C2 uses the correctness measure that passes its human-agreement gate (kappa 0.60, as in the Experiment 35 protocol). If none passes, C2 becomes exploratory. Legal RAG Bench and the defaults row get paired intervals and no confirmatory test.

The paper claims superiority only where the tests support it. No TOST margin is planned, so the paper makes no equivalence claim. A non-significant result means no difference was detected at this sample size.

What this comparison can claim: with the shared models fixed, the measured difference between two complete systems on held-out questions. Han et al. 2025 (RAG against GraphRAG) fixed the answer model, chunk size, embedding model and retrieval budget in the same way. BERGEN and FlashRAG fix shared parts inside one toolkit. The half split answers the selection-bias risk (Cawley and Talbot 2010). The defaults row and the maintainer review answer the weak-baseline risk (Yang et al. 2019).

### Pre-registration

Part 2 (C1, C2) and the A3 rule go to OSF at the same freeze as Experiment 35, before any half-B score exists.

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
   - BioASQ is CC BY 2.5.
   - Legal RAG Bench is CC BY-NC-SA 4.0. Do not release its text or derived files under CC BY. Release derived files under CC BY-NC-SA.
   - EnterpriseRAG-Bench is MIT.
   - Publish scores, question IDs and scripts that rebuild the data. Do not publish the corpus text.
4. Archive code and outputs on Zenodo with a DOI. Keep each dataset's derived files in their own archive with their own licence.
5. Before the repository or a release goes public, remove names and home-folder paths.

## Risks

| Risk | Response |
|---|---|
| A small difference between llama.cpp back ends | Every main-run pod uses one GPU type. The plan states a tolerance per metric (ADR-103). |
| A checker or the correctness judge disagrees with people | Human labels gate each one before its scores count. A measure that fails its gate becomes exploratory. |
| The run costs more than planned | The protocol ceiling stops the run at the next stage, and the operator decides. |
| The reranker result changes on llama.cpp | Report it as found. A negative result is still a result. |
| Choosing the OMRS setup inflates its score | Choose on half A by a pre-registered rule, test on half B only, and publish the search-cost figure. |
| Half B is too small to detect a difference | Report the minimum detectable effect from the data. Make no equivalence claim. |
| The single hosted answer model changes behind its ID | Pin one upstream host. Record the returned model ID and provider per call. State it as a limitation. |
| RAGFlow cannot use our models, or hides its retrieved chunks | Record the blocker and report it. Do not substitute another model. |
| RAGFlow chunks carry no page number | The pre-freeze gate checks this on a FinanceBench sample. If it fails, the primary unit is the document for every question and both systems. The page-level result is reported as a labelled sensitivity analysis. No question is dropped. |
| RAGFlow indexing costs too much GPU time | Time one RAGFlow index per dataset before the freeze. Report the cost. |
| A reviewer says we set up RAGFlow badly | Use its documented defaults, pin the release, publish the full configuration, send it to the maintainers and report the defaults row. |
| E1 indexing exceeds the budget | E1 is dropped first. Report the measured cost. |
| Public leaderboard results lack per-question scores | E1 is descriptive. Do not infer significance from rank or aggregate scores. |
| The journal deal does not cover the article type | Ask the library before writing. Research Article is the fallback. |

## Next steps

1. Done: pipeline sweep (Step 1), archived 8 November 2026.
2. Done: `pdf-inspector-page-provenance` (page numbers from the default reader).
3. Done: Experiment 35 amendments A1, A2 and A2c.
4. Ask the Napier library to confirm the article type and the deal.
5. Done: Experiment 35 amendment A3 (protocol section 0.12) holds the selection rule for Part 2.
6. Reserve an experiment number for Part 2. Write its protocol: C1, C2, the fairness rules and A3 as reference.
7. Before the freeze, pin the RAGFlow release and container digest and connect it to the llama.cpp models. Time one index per dataset. Check page provenance on a seeded FinanceBench sample (the rule 3 gate: if RAGFlow returns no page for a chunk, the primary unit falls back to the document for both systems) and retrieval repeatability. Send the configuration to the RAGFlow maintainers.
8. Done: group 7 (Part 2 and E1) is in `rag-benchmark-readiness-flow`.
9. Freeze Part 1. Deposit Experiment 35, Part 2 and A3 on OSF together.
10. Before any E1 run, estimate its cost and ceiling. Pin the corpus and leaderboard revisions. Confirm the GPT-5.4 judging or submission procedure with Onyx.

## Sources checked on 27 October, 9 November, 12 November and 13 November 2026

- FinanceBench, arXiv 2311.11944.
- FreshStack, arXiv 2504.13128.
- MedRAG and MIRAGE, arXiv 2402.13178.
- BEIR, arXiv 2104.08663.
- Ragas, arXiv 2309.15217. Version 0.4.3 on PyPI is dated 13 January 2026.
- Miller 2024, "Adding Error Bars to Evals", arXiv 2411.00640.
- Smucker, Allan and Carterette 2007, CIKM, doi:10.1145/1321440.1321528 (to verify).
- Urbano, Lima and Hanjalic 2019, SIGIR, arXiv 1905.11096 (choice of statistical test in IR evaluation).
- Cawley and Talbot 2010, JMLR, "On over-fitting in model selection and subsequent selection bias in performance evaluation".
- Yang, Lu, Yang and Lin 2019, SIGIR, doi:10.1145/3331184.3331340 (weak baselines).
- Dodge et al. 2019, EMNLP, "Show your work", arXiv 1909.03004 (expected validation performance; to verify).
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
