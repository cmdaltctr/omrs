# Experiment 35: Reproducible Local RAG Benchmark of OMRS

> Status: DRAFT. Purpose `publication`, size Confirmatory. Commit `protocol.md` and `plan.json` before the first measured run.

## Pre-freeze amendment A1 (2026-11-12)

The operator and the agent agreed a full redesign before the freeze. It wins over the older text below, which stays for history. Design section D0 holds the detail.

- **Datasets (English only, 1,160 questions):** FinanceBench (`PatronusAI/financebench`, 150), FreshStack LangChain (203 public queries, not 223; the 20 Experiment 9 continuity queries leave), BioASQ mini (707) and Legal RAG Bench (`isaacus/legal-rag-bench`, 100 expert questions, one gold passage each, 4,876 passages, CC BY-NC-SA 4.0; exploratory because of low power). LegalBench-RAG and LLeQA are out. FinanceBench answers also get a number-match check.
- **Search stage, full factorial on all four datasets:** embedder (Qwen3-Embedding 0.6B, 4B, 8B) x chunk size (512, 1,024, 2,048 Qwen3 tokens, overlap 15%: 77, 154, 307, the same for Markdown and plain text) x reranker (off, Qwen3-Reranker 0.6B, 4B, 8B) x hybrid (off, on with BM25 pinned). That is 9 indexes per dataset and 72 search setups. Setups are named by their settings, never by a profile name.
- **Dropped:** the six one-factor arms, the `chunking-off` arm, MiniLM (it truncates at 512 tokens), Granite Guardian, hypothesis H-CC, the $250 cap. Isnad moved to v4.
- **Hypotheses H1 to H7** (search) and **H8** (answer stage, chunk size against faithfulness and correctness), each with a paired test and Holm correction.
- **Answer stage:** one embedder and one reranker size, chosen by a rule fixed before the run; then chunk size x reranker on or off x hybrid on or off = 12 crossed setups (plus 3 token-matched setups from A2 and A3, 15 in all) x 3 runs x 1,160 questions. Answer model, Ragas judge and claim checkers GLM-5.3 (main) and Clef-Flash (second) as before. The refusal rule stays.
- **Budget:** re-estimated at about $650, with a stop rule at a ceiling of $975 (1.5 x the estimate).
- **Hardware:** one GPU type for every main-run pod, chosen before the freeze from a 10-minute timing job on RTX 4090, L40S and H100 by a rule written before measuring. The 9 indexes build on parallel pods of that type.
- **New OMRS code:** a llama.cpp reranker backend (one new file and one `register()` line) in change `exp35-main-run-readiness`.

## Pre-freeze amendment A2 (2026-11-13)

An independent methods review ran; the operator approved every fix (design D0.12): unit-level scoring after collapsing the top 100 chunks; token-matched controls; H6 confirmatory on FinanceBench and FreshStack only, Legal exploratory throughout; one mixed model per dataset with a 2-of-3 cross-dataset rule; MDE from data; split-half selection; two labellers; a closed-book run; returned-model provenance; reranker rank checks; OSF pre-registration. Budget about $650, ceiling $975.

## Why

OMRS needs one benchmark of the full pipeline that a paper can cite. Past experiments (1 to 43) were optimisation runs. Many used Ollama, small question sets or remain unfinished, so they cannot be cited as they are.

ADR-103 now gives a reproducible runtime: every local model runs through llama.cpp with a public GGUF file and a pinned build. It also adds the `publication` purpose, which the experiment checker enforces.

This change turns Experiment 35 into the benchmark for the first fellowship paper (`docs/proposals/first-publication-benchmark.md`). The claim is modest and testable: on these public benchmarks, with these pinned models, OMRS reaches these scores, and these pipeline choices change them by these amounts.

## What Changes

- Make Experiment 35 a `publication` experiment of size Confirmatory. `plan.json` holds a pinned `runtime` block (ADR-103). A live-server check runs before the first score of each run.
- Use three public datasets from three domains:
  - FinanceBench open sample: all 150 questions, real PDFs, hit at gold document and gold page.
  - FreshStack LangChain slice: all 223 queries, a new index, chunks mapped to parent documents.
  - BioASQ (`enelpol/rag-mini-bioasq`, test split): 707 questions, 40.2K PubMed abstracts. Fallback: NFCorpus, retrieval scores only.
- Run six arms on the same questions. The baseline is the `documents` profile with Qwen3-Embedding-4B (local GGUF). Each ablation changes one component: embedding 0.6B, embedding 8B, reranker off, token-aware chunking off, hybrid search. Answers come from Qwen3-4B (local GGUF), with `deepseek/deepseek-v4.1-flash-1017` as the stated fallback. Metadata extraction is off in every arm.
- Run each arm 3 times. Retrieval must give the same result each run (determinism check). The 3 runs measure answer, judge and latency variation.
- Report gold-label retrieval metrics as primary: Recall@10, MRR@10, nDCG@10, and hit@page for FinanceBench. Report Ragas 0.4.3 as secondary only.
- Use a fixed statistics set: confidence intervals, paired differences from the baseline, paired tests, Holm correction, wins/losses/ties, and a minimum detectable effect stated before the run.
- Add the publication rules that change the experiment: a shareable example set, a split between shareable and restricted outputs, licence-aware release, Zenodo archives, and removal of personal identifiers.
- Run locally or on rented cloud hardware. Decide after the embedding timing. Both options use the same GGUF files, the same build and the ADR-103 tolerance.
- Move RepoProbe (old 35B-1) to a later paper. It has no retrieval labels and needs an LLM judge for every score.
- Keep: no production default changes, Ragas and observability tooling outside the base install, per-stage JSONL traces, no framework comparison inside this experiment (the RAGFlow comparison is Part 2, amendment A3).

## Dependency

The pipeline sweep (`openspec/changes/pipeline-sweep-llamacpp/`, optimisation, Standard) runs first. It checks every stage on llama.cpp after the move off Ollama. Experiment 35 freezes its protocol only after the sweep passes its exit rule.

## Datasets and licences

| Dataset | Domain | Questions | Corpus | Gold labels | Licence |
|---|---|---|---|---|---|
| FinanceBench (open sample) | Finance, real PDFs | 150 | 10-K and similar filings | Gold document and page | CC BY-NC 4.0 |
| FreshStack, LangChain slice | Software | 223 | 10,024 documents | Gold documents | CC BY-SA 4.0 |
| BioASQ (`enelpol/rag-mini-bioasq`, test split) | Biomedicine | 707 | 40.2K PubMed abstracts | Gold passages and reference answers | CC BY 2.5 |
| NFCorpus (fallback for BioASQ) | Biomedicine | (check) | (check) | Graded relevance | Check the academic-use terms first |

Publish scores, question IDs and rebuild scripts. Do not publish corpus text. Task 1.3 rechecks each licence at the frozen revision.

No open medical dataset has real PDFs with page-level gold evidence. FinanceBench is the PDF arm.

## Capabilities

### New Capabilities

- `document-rag-evaluation`: the benchmark contract for FinanceBench and BioASQ (datasets, arms, primary metrics, the page hit rule, frozen identities).
- `codebase-rag-evaluation`: the benchmark contract for FreshStack retrieval (new index, parent-document mapping, Experiment 22 as a reference only). RepoProbe answer scoring is no longer part of it.
- `evaluation-observability`: shared runtime pinning, traces, repetitions, statistics, Ragas isolation and the data-sharing rules.

### Modified Capabilities

- None.

## Impact

- Experiment and evaluation artefacts only. New code lives in `experiments/35-*/` and `experiments/_lib/`.
- `experiments/_lib/retrieval_metrics.py` gains plain nDCG@10 and hit@page. Existing metric definitions do not change.
- No production API or packaged default changes.
- Ragas goes in a separate `uv` dependency group, outside the base install and every published extra.
- The reservation text for number 35 in `experiments/reserved.json` describes the old two-baseline plan. Update it when the folder is created (task 3.1).
