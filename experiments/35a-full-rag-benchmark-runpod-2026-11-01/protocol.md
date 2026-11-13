# Experiment 35a: Reproducible local RAG benchmark of OMRS (RunPod)

> Superseded (2026-11-13) by Experiment 35 (`35-full-rag-benchmark-2026-11-01`) and its amendments A1 to A3. Experiment 35 now runs on RunPod. This file is kept for history. Do not run it.

- **Folder**: `35a-full-rag-benchmark-runpod-2026-11-01`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with AI agent (plan draft; the operator confirms the open values at freeze).
- **Related**: Experiment 35 (`35-full-rag-benchmark-2026-11-01`), the same benchmark planned for the local Mac; it stays at PLANNED for a possible local run and is never mixed with this run's numbers. ADR-103 (llama.cpp GGUF runtime), ADR-018 (documents profile), ADR-063 (token-aware chunking), change `experiment-35-full-document-rag-benchmark`, `docs/proposals/first-publication-benchmark.md`. Carries forward Experiments 2, 3, 10b, 15, 22 and 25. Experiment 22 is a reference only, not a baseline.

## 1. Question

What retrieval and answer quality does the full OMRS pipeline reach on three public benchmarks with pinned local models, and how much do four pipeline choices change it (embedding size, reranker, token-aware chunking, hybrid search)?

The first fellowship paper cites these numbers. The experiment changes no production default; a finding that suggests one goes to a separate proposal. This edition runs the measured pass on rented GPU hardware (RunPod); Experiment 35 holds the local-Mac edition of the same plan.

## 2. Hypothesis

One hypothesis per ablation arm and dataset. The primary endpoint is nDCG@10.

- **H1 (primary, all five ablation arms)**: the arm's nDCG@10 differs from the baseline's on at least one dataset.
- **H0 (null)**: the arm's nDCG@10 equals the baseline's; any observed difference is within the minimum detectable effect.
- **Decision rule**: a difference counts when the Holm-adjusted p (within one dataset, across its arms) is below 0.05 and the paired 95% bootstrap interval on the difference excludes zero. Otherwise the report says "no difference larger than the minimum detectable effect was found".

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

Fixed in every arm: the datasets and question order, the answer model (Qwen3-4B Q8_0 through llama.cpp, temperature 0, seed 20261101, thinking setting pinned at freeze), metadata extraction `disabled`, 3 repetitions per arm, and one index per arm (the hybrid and reranker arms reuse the baseline index).

Measured: Recall@10, MRR@10, nDCG@10, hit@page (FinanceBench only), Ragas 0.4.3 secondary metrics, latency p50 and p95 per query, and the ingestion diagnostics of design D4.

## 4. Data

| Item | FinanceBench (open sample) | FreshStack (LangChain slice) | BioASQ (`enelpol/rag-mini-bioasq`, test split) |
| --- | --- | --- | --- |
| Questions | 150 | 223 | 707 (or the frozen subset) |
| Corpus | Real 10-K and similar filings, full PDF path | About 10,024 parent documents | 40.2K PubMed abstracts |
| Gold labels | Gold document and gold page (`evidence_page_num`, zero-indexed) | Gold documents | Gold passage IDs and reference answers |
| Unit | Question | Query | Question |
| Licence | CC BY-NC 4.0 | CC BY-SA 4.0 | CC BY 2.5 |
| Already seen | New | Experiments 9a and 22 | New |

- The FreshStack slice is the `prepare_freshstack.py` export, seed 20260530. Task 1.6 records the corpus and qrels hashes.
- Task 1.2 records the FinanceBench revision and the SHA-256 of each PDF. Task 1.7 records the BioASQ revision and hashes. The PDFs and derived text stay out of git and out of any CC BY release.
- Fallback for BioASQ: NFCorpus (`BeIR/nfcorpus`), retrieval scores only. Task 1.8 checks its academic-use terms first.
- A question stays in its denominator even when its pipeline stage fails.

## 5. Steps

Run every command on the RunPod pod, from the repository root. The harness scripts are built by change tasks 2.1 to 2.10 before the freeze.

1. Prepare the data: `uv run --no-sync python experiments/35a-full-rag-benchmark-runpod-2026-11-01/prepare_data.py` (FinanceBench download, FreshStack export seed 20260530, BioASQ download; records revisions and hashes). On the pod, download or copy the frozen inputs and verify every SHA-256 before the run.
2. Start one `llama serve` router on `127.0.0.1` of the RunPod pod (RTX 4090, CUDA build 11671), one preset per model of the runtime table.
3. Run: `uv run --no-sync python experiments/35a-full-rag-benchmark-runpod-2026-11-01/run_arm.py --arm NAME --dataset DATASET --run N --resume` (six arms, three datasets, 3 runs each; appends the run record and writes JSONL traces).
4. Determinism and rebuild checks: `uv run --no-sync python experiments/35a-full-rag-benchmark-runpod-2026-11-01/check_determinism.py` (runs 2 and 3 against run 1; one 4B baseline rebuild per dataset in a fresh process).
5. Summarise: `uv run --no-sync python experiments/35a-full-rag-benchmark-runpod-2026-11-01/summarise.py` (expert statistics from `plan.json`; writes `output/summary.json` and the report tables).

The smoke subset (task 4.1) runs on the pod, on a small slice of each dataset through every arm, before the freeze. It also verifies the PDF reader and the OCR routing path on Linux CUDA, which has never run off the Mac. It is never scored as a result.

## 6. Analysis

- **Stats level**: expert.
- **Tests**: paired permutation test on per-question nDCG@10 (10,000 shuffles, seed 20261101), averaged over the 3 runs per question first. McNemar's exact test for hit@page hit or miss. Wilson intervals for rates, paired bootstrap (10,000 resamples) for differences and means. `holm` correction across the arms of one dataset, on nDCG@10 only. Functions come from `.agents/skills/s-experiment/references/stats.py` and `experiments/_lib/stats.py`; no new statistics code.
- **Minimum detectable effect**: about 4 points at 150 to 223 questions; about 2 points at 707 questions. Stated before the run; recorded per dataset in the report.
- **Sensitivity**: re-test the 0.05 cut-off at 0.045 and 0.055 and report whether any arm's verdict changes.
- **Gates**:

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | Runs 2 and 3 retrieve exactly what run 1 retrieved on the fixed index, every arm and dataset | A mismatch breaks the paired design and is itself a finding |
| G2 | The 4B baseline index rebuilt once per dataset in a fresh process gives run 1's retrieved lists | Shows index building is repeatable |
| G3 | `verify_llamacpp_runtime` passes before the first score of every run | A wrong build or file hash invalidates every score |

- **Stop rule**: the run is complete when every arm and dataset has 3 runs, the determinism and rebuild checks, and the Ragas pass. Stop early when the preflight fails, a gate fails, or the smoke subset exceeds the task 1.11 budget on extrapolation. A determinism mismatch is recorded and reported, never swapped for another run.
- **What each outcome means**:
  - Pass: gates hold; the report states each arm's difference or "no difference larger than the minimum detectable effect".
  - Fail: a gate failed; investigate before any number is cited in the paper.
  - Unclear: an interval crosses zero; report it as not shown, not as no effect.

## 7. Runtime

- **Purpose**: publication. **Runtime under test**: no.
- **Machine (task 1.5 decision, 2026-11-01)**: RunPod Secure Cloud, on-demand RTX 4090 (24 GB VRAM, 41 GB RAM, 6 vCPUs), per-second billing, one volume disk for models, datasets and indexes. Backend CUDA. Reason: the answer stage dominates the wall time (19,440 answer runs); the Mac estimate is 4 to 8 days, one RTX 4090 about 1 to 2 days. Budget: about 24 to 40 pod-hours, roughly $20 to $35 all in (RunPod pricing page, checked 2026-11-01: RTX 4090 Secure Cloud $0.69/hr, volume $0.10/GB/month running). Every run record names this machine. All arms of one dataset run on this one machine, so the paired comparisons stay fair; no number from this run mixes with Mac numbers.
- **Local models**: every one runs through llama.cpp (`llama serve` router, one preset per model). No Ollama, no MLX. Build 11671 exactly; another build needs a plan amendment first. On the pod, the same release 11671 is compiled for CUDA by a Dockerfile or build script pinned with the harness (change section 2); the live check verifies build and file hashes on the pod exactly as locally.

| Role | Repository | File | SHA-256 | Build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Embedding baseline 4B | `Qwen/Qwen3-Embedding-4B-GGUF` | `Qwen3-Embedding-4B-Q8_0.gguf` | `b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d` | 11671 | `--embeddings --pooling last --ctx-size 8192 --ubatch-size 8192` |
| Embedding 0.6B | `Qwen/Qwen3-Embedding-0.6B-GGUF` | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` | 11671 | as baseline |
| Embedding 8B | `Qwen/Qwen3-Embedding-8B-GGUF` | `Qwen3-Embedding-8B-Q8_0.gguf` | `d20ddc71e8a5c4344f2343481e242233a997dc5eaff442427a945836c97b4deb` | 11671 | as baseline |
| Answer | `Qwen/Qwen3-4B-GGUF` | `Qwen3-4B-Q8_0.gguf` | `8c2f07f26af9747e41988551106f149b03eb9b5cb6df636027b6bf6278473300` | 11671 | `--ctx-size 16384`; temperature 0 and seed 20261101 per request |

The ONNX reranker and the OCR engines do not run through llama.cpp. The freeze records them under the runtime manifest with name, revision and file hash. The embedding tokenizer (`Qwen/Qwen3-Embedding-4B`, `tokenizer.json`, revision `5cf2132a`) is the token-aware chunking tokenizer, cached and hash-checked by sweep task 2.4a.

- **Hosted references**: main Ragas judge `deepseek/deepseek-v4.1-flash-1017` (OpenRouter, temperature 0, fixed seed, one pinned upstream provider); cross-check judge `openai/gpt-6.1-terra` (OpenRouter, fixed seed, 50 hand-checked items). A judge never scores its own model family.
- **Tolerance**: 0.005 absolute on each primary metric (Recall@10, MRR@10, nDCG@10, hit@page). The largest change that still counts as the same result on another back end. Confirm or change at freeze.
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score of each run and passes `runtime=found.as_run_record()` to `record_run_start`. A mismatch stops the run.
- **Storage and teardown**: the pod volume holds models, datasets and indexes. After the run, copy `output/` to `DATA/omrs/` with SHA-256 receipts, then destroy the pod and its volume; idle volume storage bills at double the running rate.
