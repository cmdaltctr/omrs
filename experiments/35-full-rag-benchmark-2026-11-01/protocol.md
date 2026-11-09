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

Fixed in every arm: the datasets and question order, the answer model (Qwen3-4B Q8_0 through llama.cpp, temperature 0, seed 20261101, thinking setting pinned at freeze), metadata extraction `disabled`, 3 repetitions per arm, and one index per arm (the hybrid and reranker arms reuse the baseline index).

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
