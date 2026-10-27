# Experiment 35: Reproducible Local RAG Benchmark of OMRS

> Status: DRAFT. Purpose `publication`, size Confirmatory. Commit `protocol.md` and `plan.json` before the first measured run.

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
- Keep: no production default changes, Ragas and observability tooling outside the base install, per-stage JSONL traces, no framework comparisons.

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
