# Experiment 35: Reproducible local RAG benchmark of OMRS

- **Folder**: `35-full-rag-benchmark-2026-11-01`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: Aizat, with the a-build agent (plan draft; the operator confirms the open values at freeze).
- **Related**: ADR-103 (llama.cpp GGUF runtime), ADR-018 (documents profile), ADR-063 (token-aware chunking), change `experiment-35-full-document-rag-benchmark`, `docs/proposals/first-publication-benchmark.md`. Carries forward Experiments 2, 3, 10b, 15, 22 and 25. Experiment 22 is a reference only, not a baseline.

## 1. Question

What retrieval and answer quality does the full OMRS pipeline reach on three public benchmarks with pinned local models, and how much do four pipeline choices change it (embedding size, reranker, token-aware chunking, hybrid search)?

The first fellowship paper cites these numbers. The experiment changes no production default; a finding that suggests one goes to a separate proposal.

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
- **Selection rule (fixed before the main run).** The main claim checker is the candidate with the highest LLM-AggreFact average balanced accuracy on the full test split, scored by the leaderboard rule. A local checker replaces it only if it lands within 2 points of it on both the average and RAGTruth and also judges more rows per second; both conditions must hold, because the 2-point allowance exists only to buy speed and cost. Today this selects GLM-5.3: Granite is within 2 points but slower (2.3 against about 2.8 rows per second). Its figure is our own measurement (outputs published); it may have seen LLM-AggreFact data in training.
- **Main checker: GLM-5.3.** On the Experiment 20 set of 120 triples, reasoning `low` gave recall 1.0 and false rejection 0.0.
- **Second checker and fallback: Granite Guardian.** If GLM-5.3 calls fail, the run stops and resumes with `--resume` when Z.AI is back; the runner never switches checker by itself. If GLM-5.3 is withdrawn for good, the operator names Granite main in a dated amendment. Granite has already judged every claim, so nothing is re-run.
- **Reported as data: Clef-Flash.** A 1,000-row run on the original weights decides whether a question fix and a full re-run are worth doing. It becomes main only by the selection rule (average 74.9 or higher and RAGTruth 83.1 or higher, full split, after the fix).
- **No sampling.** All three checkers judge every claim in every arm and every run (`run_arms.py --judges clef_flash,granite_guardian,chat`). If Granite's speed strains the budget, the freeze adds pod time or a second pod; coverage is never cut. The report gives each checker's faithfulness per arm and Cohen's kappa of Granite and of Clef-Flash against GLM-5.3 on all claims.
- **Why 2 points.** The claim checker sets the faithfulness scores. Its shortfall against the reference checker (GLM-5.3) must stay well below the minimum detectable effect between arms (about 4 points), or it could hide or invent a difference between arms. We set the bar at 2 points (half the MDE) on both the average and RAGTruth balanced accuracy, on the full split, where sampling noise is well under 1 point. 1 point was rejected: leaderboard models treated as equivalent already differ by about 1 point (Clef-Flash 76.6, Granite 76.5, gpt-4o 75.9), and our Granite reproduction landed 0.8 below and 1.0 above its published pair. 3 points was rejected: it approaches the MDE and spans a full leaderboard tier (gpt-4o 75.9, gpt-4o-mini 74.0). The report says "on par" only at a gap of about 1 point or less (as MiniCheck, EMNLP 2024); for a gap between 1 and 2 points it says "slightly lower accuracy" with the numbers. It gives every checker's balanced accuracy beside speed and cost: GLM-5.3 76.9 at about 2.8 rows/s, hosted; Granite 75.7 at 2.3 rows/s, local; Clef-Flash 67.8 at 7.5 rows/s, local, about $0.95 of pod time per full split.
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
- **Local models**: every one runs through llama.cpp on OMRS's managed router (`llama-server`, one preset per model). No Ollama, no MLX. Build b11941 exactly (readiness flow task 5.2); another build needs a plan amendment first. `plan.json` holds the same rows.

| Role | Repository | File | SHA-256 | Build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| Embedding baseline 4B | `Qwen/Qwen3-Embedding-4B-GGUF` | `Qwen3-Embedding-4B-Q8_0.gguf` | `b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d` | 11941 | `--embeddings --pooling last --ctx-size 8192 --batch-size 8192 --ubatch-size 8192` |
| Embedding 0.6B | `Qwen/Qwen3-Embedding-0.6B-GGUF` | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` | 11941 | as baseline |
| Embedding 8B | `Qwen/Qwen3-Embedding-8B-GGUF` | `Qwen3-Embedding-8B-Q8_0.gguf` | `d20ddc71e8a5c4344f2343481e242233a997dc5eaff442427a945836c97b4deb` | 11941 | as baseline |
| Claim checker, Clef-Flash | `ggml-org/Clef-Flash-GGUF` | `Clef-Flash-Q8_0.gguf` | `25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e` | 11941 | `--ctx-size 32768 --batch-size 32768 --ubatch-size 32768 --parallel 1` |
| Claim checker, Granite Guardian | `ibm-granite/granite-guardian-3.3-8b-GGUF` | `granite-guardian-3.3-8b-Q8_0.gguf` | `356fc80d343a699a3d12316de161d4341ee2d11f7057123dabb158804e876bc5` | 11941 | as Clef-Flash |

The ONNX reranker and the OCR engines do not run through llama.cpp. The freeze records them under the runtime manifest with name, revision and file hash. The embedding tokenizer (`Qwen/Qwen3-Embedding-4B`, `tokenizer.json`, revision `5cf2132a`) is the token-aware chunking tokenizer, cached and hash-checked by sweep task 2.4a.

- **Hosted references** (section 3, ADR-119): answer model `deepseek/deepseek-v4.1-flash-1017` (OpenRouter, temperature 0, seed 20261101, one pinned upstream host); main Ragas judge `openai/gpt-oss-120b` (OpenRouter, reasoning `low`, temperature 0, fixed seed, one pinned upstream host); cross-check judge `openai/gpt-6.1-terra` (OpenRouter, fixed seed, 50 hand-checked items); main claim checker GLM-5.3 (Z.AI, section 4.4). A judge never scores its own model family.
- **Tolerance**: 0.005 absolute on each primary metric (Recall@10, MRR@10, nDCG@10, hit@page). The largest change that still counts as the same result on another back end. Confirm or change at freeze.
- **Live check**: the runner calls `verify_llamacpp_runtime` before the first score of each run and passes `runtime=found.as_run_record()` to `record_run_start`. A mismatch stops the run.
