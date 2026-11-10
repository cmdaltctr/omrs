# Tasks: Experiment 35 Reproducible Local RAG Benchmark

> DRAFT. Do not start a measured run until section 4 is complete and committed. Section 1 starts only after `pipeline-sweep-llamacpp` passes its exit rule.

## 1. Prepare the protocol inputs

- [x] 1.1 Confirm that `pipeline-sweep-llamacpp` passed its exit rule. Record the sweep report path in the protocol. Verify: the sweep report shows every stage without error. Done 2026-11-09: Exp 48 report `experiments/48-pipeline-sweep-llamacpp-2026-11-01/report.md` shows G1 to G3 pass; recorded in protocol header.
- [x] 1.2 Download the FinanceBench open sample (150 questions and source PDFs) to `DATA/omrs/`. Record the revision and the SHA-256 of each PDF. Verify: 150 questions load and every gold `evidence_doc_name` has a PDF. Done 2026-11-09 (re-verified, no download): 150 questions, 84 PDFs, all hashes match; protocol section 4.1.
- [x] 1.2a Count table-text loss on the FinanceBench PDFs before corpus ingest (issue 197). For each PDF, compare the reader's per-page text against the page's table areas; count pages where most table text is missing. If more than 5 percent of pages are affected, OCR those source pages during corpus prep and record the choice in the protocol. This is a corpus-prep step, not a reader code change. Verify: the protocol holds the per-PDF count and the OCR decision with its reason. Done 2026-11-09: under 1 percent of pages affected for every reader, no OCR; protocol section 4.3.
- [x] 1.3 Record the revision, licence and download procedure of each dataset. Recheck each licence against the proposal table. Keep FinanceBench out of git. Verify: the protocol lists one licence line per dataset with the date checked. Done 2026-11-09 for the three datasets: protocol section 4.2.
- [x] 1.4 Time local Qwen3-Embedding 0.6B, 4B and 8B (GGUF, same quantisation) on a fixed slice of each corpus. Record wall time, tokens and peak memory, and extrapolate to each full corpus. Reuse the `pipeline-sweep-llamacpp` timing when it exists for the same machine and files. Verify: the protocol holds one timing row per model and corpus, with its source. Done 2026-11-10: protocol section 4.5 (4B from the pre-freeze pod, 0.6B and 8B from Exp 48; 2.9 h, 3.4 h, 3.7 h per full build).
- [x] 1.5 Decide local or rented cloud hardware from the 1.4 timing. If local 4B does not fit, make OpenRouter `qwen/qwen3-embedding-4b` the named hosted reference arm. Verify: the protocol names the machine, the back end and the reason. Done 2026-11-10: RunPod secure RTX 4090, llama.cpp b11941 CUDA; protocol section 4.5.
- [x] 1.6 Export the FreshStack LangChain slice with `prepare_freshstack.py` (seed 20260530). Record the corpus and qrels hashes. Verify: 223 queries and about 10,024 parent documents load. Done 2026-11-09 from the existing 9a export (no re-export, no download; HF revisions never recorded, inference stated): 223 queries, 10,024 rows plus one overlay file; protocol section 4.1.
- [x] 1.7 Download BioASQ `enelpol/rag-mini-bioasq` (test split). Record the revision and hashes. If 1.4 shows it does not fit, define a question-type subset. Verify: 707 questions (or the frozen subset) load with gold passage IDs. Done 2026-11-09 (re-verified, no download): 707 questions, 40,181 passages; protocol section 4.1.
- [x] 1.8 If BioASQ cannot be used, check the NFCorpus academic-use terms before use. Verify: the protocol records the terms check, or records that the fallback is not used. Done 2026-11-09: BioASQ usable, fallback not used; protocol section 4.1.
- [ ] 1.9 For each dataset, check which documents route through the Markdown splitter. Mark the chunking arm "not applicable" where it changes no chunk. Reuse the trial run's chunking guard: every arm except token-aware chunking off stops unless the splitter resolves to `model_token_aware`. Verify: the protocol lists the chunking arm state per dataset, and the guard test fails on an uncached tokenizer.
- [x] 1.10 Choose the answer model and the Ragas judge model, through llama.cpp when possible. Record the agreement measure for the 50-item hand check. Verify: the protocol names both models and the agreement measure. Done 2026-11-10: hosted DeepSeek answers and `openai/gpt-oss-120b` judge (operator, 2026-11-08), GLM-5.3 claim checker; kappa measure; protocol sections 3 and 4.4, ADR-119.
- [ ] 1.11 Define the wall-time, memory and paid-provider budget. Verify: the protocol states each limit with a number.

## 2. Build the shared harness (test-first)

- [x] 2.1 Write a failing test for plain nDCG@10 and hit@page in `experiments/_lib/retrieval_metrics.py`, with known lists, including a merged row with `page_labels` `["5", "6"]` and gold page 6, which counts as a hit. hit@page reads `page_labels`, with `page_label` as the fallback. Then add the functions without changing existing definitions. Verify: the new tests fail before the change and pass after it; existing metric tests still pass. Done 2026-11-10 on `feat/exp35-shared-harness`: tests/test_experiment_lib_retrieval_metrics.py; local CI green.
- [x] 2.2 Write a failing unit test for the FinanceBench page conversion on a known page. Then add one conversion function. Verify: the test fails without the conversion and passes with it. Done 2026-11-10 on `feat/exp35-shared-harness`: gold_rules page conversion, tests/test_experiment_lib_gold_rules.py; local CI green.
- [x] 2.3 Write a failing test for the FreshStack parent mapping (three chunks of one parent count once). Then reuse the Experiment 22 mapping code. Verify: the test passes and Recall@10 counts the parent at its first rank. Done 2026-11-10 on `feat/exp35-shared-harness`: gold_rules parent mapping, same test file; local CI green.
- [x] 2.4 Write a failing test for the BioASQ passage hit rule. Then add the rule. Verify: a gold passage ID in the top 10 counts as a hit. Done 2026-11-10 on `feat/exp35-shared-harness`: gold_rules passage hit, same test file; local CI green.
- [x] 2.5 Make the statistics functions in design D6 importable from the experiment. Copy them unchanged only if import fails, with their tests. Verify: a test calls each function on a known input and matches the s-experiment reference output. Done 2026-11-10 on `feat/exp35-shared-harness`: experiments/_lib/stats_d6.py, byte-identical copy checked against the skill, tests/test_experiment_stats_d6.py; local CI green.
- [x] 2.6 Write a failing test that the trace writer never writes to stdout and that a failed query keeps its row. Then add the JSONL trace writer (design D8). Verify: the test passes; a sample trace holds every D8 field. Done 2026-11-10 on `feat/exp35-shared-harness`: experiments/_lib/trace.py, tests/test_experiment_trace.py; local CI green.
- [x] 2.7 Write a failing test that a run with a wrong GGUF hash stops before scoring. Then wire `verify_llamacpp_runtime` and `record_run_start(..., runtime=...)` into the harness. Verify: the test passes against a stub server. Done 2026-11-10 on `feat/exp35-shared-harness`: experiments/_lib/run_guard.py, tests/test_experiment_run_guard.py; local CI green.
- [x] 2.8 Write a failing test that compares the retrieved lists of runs 1, 2 and 3 and reports any mismatch. Then add the determinism check. Verify: an injected difference is reported with its size. Done 2026-11-10 on `feat/exp35-shared-harness`: experiments/_lib/determinism.py, tests/test_experiment_determinism.py; local CI green.
- [x] 2.9 Run a dry resolve with Ragas 0.4.3 in a separate `uv` dependency group. Check `tests/test_dependency_floors.py`. Then add the group. Verify: `uv sync` without the group does not install Ragas; the fast suite passes. Done 2026-11-10 on `feat/exp35-shared-harness`: `ragas` dependency group (ragas 0.4.3, langchain-community 0.3.31); plain sync has no ragas; local CI green.
- [x] 2.10 Write a failing test that a file with corpus text under `output/shareable/` fails the release check, and that a home-folder path fails it. Then add the check. Verify: both cases fail; a clean folder passes. Done 2026-11-10 on `feat/exp35-shared-harness`: experiments/_lib/release_check.py, tests/test_experiment_release_check.py; local CI green.

## 3. Create the experiment record

- [x] 3.1 Create the folder with `uv run --no-sync omrs experiments new full-rag-benchmark --title "Reproducible local RAG benchmark of OMRS" --category retrieval --size Confirmatory --purpose publication`. Update the number 35 reservation text in `experiments/reserved.json`. Verify: `omrs experiments check` reports no error for the folder.
- [x] 3.2 Write `plan.json` with the ADR-103 `runtime` block: every local model, the hosted references and a tolerance per primary metric. Verify: `load_runtime_block` accepts it and the checker reports no `publication-*` error.
- [x] 3.3 Write `protocol.md`: datasets, arms, metrics, the 3-run policy, the statistics plan, hypotheses, null, decision rule and the minimum detectable effect per dataset. Verify: every section of design D2 to D6 has a matching protocol section.
- [ ] 3.4 Build the shareable example set: example input, expected output and a reading guide. Use only data whose licence allows sharing. Verify: the release check in 2.10 passes on it.

## 4. Freeze

- [ ] 4.1 Run a small smoke subset of each dataset through every arm. Do not score it as a result. Verify: every stage writes traces without error and the budget in 1.11 is not exceeded on extrapolation.
- [ ] 4.2 Commit `protocol.md` and `plan.json`. Verify: the commit exists before the first line of `output/run-records.jsonl`.
- [ ] 4.3 Remove DRAFT status from this change. Verify: the status line names the freeze commit.

## 5. Run

- [ ] 5.1 Run the six arms (or fewer, where 1.9 marks a cell not applicable) on FinanceBench, 3 runs each. Verify: one run record per run, each with a passed live-server check.
- [ ] 5.2 Run the arms on FreshStack, 3 runs each, with a new index per embedding or chunking arm (the reranker and hybrid arms reuse the baseline index). Verify: as 5.1, and each run indexes the frozen corpus hash.
- [ ] 5.3 Run the arms on BioASQ (or the frozen subset or fallback), 3 runs each. Verify: as 5.1.
- [ ] 5.4 Run the determinism check for every arm, and the rebuild check (4B baseline index rebuilt once per dataset in a fresh process). Verify: the output states match or mismatch per arm and dataset, and for each rebuild.
- [ ] 5.5 Run Ragas on each arm where the dataset supports each metric. Verify: unsupported metrics show "not measured".
- [ ] 5.6 Check about 50 judged items by hand. Verify: the agreement is computed with the measure frozen in 1.10.

## 6. Analyse and report

- [ ] 6.1 Compute the design D6 statistics per dataset and arm, averaging 3 runs per question first. Verify: every number in the result tables comes from a named `output/` file.
- [ ] 6.2 Write `report.md` with the Answer box, one table per dataset in the proposal layout, the determinism result, run-to-run SD, hand-check agreement and limitations. Report Experiment 22 as a reference only. Verify: `omrs experiments check` passes and every number names its source file.
- [ ] 6.3 Update `status` and `finding` in `experiment.json`, then rebuild the index with `omrs experiments index --write`. Verify: the index row shows the new status.

## 7. Release

- [ ] 7.1 Split `output/` into `shareable/` and `restricted/`. Verify: the release check passes on `shareable/`.
- [ ] 7.2 Copy `output/` to `DATA/omrs/experiments/` with SHA-256 checksums. Verify: the checksums match and the copy is listed in `DATA_LOCATIONS.md`.
- [ ] 7.3 Archive code and shareable outputs on Zenodo with a DOI. Give each dataset's derived files their own archive and licence. Verify: each archive shows the right licence and no corpus text.
- [ ] 7.4 Search every upload for names and home-folder paths before it goes public. Verify: the search returns no hit.
- [ ] 7.5 Send any production setting change suggested by the results to a separate proposal. Verify: this change modifies no production default.
