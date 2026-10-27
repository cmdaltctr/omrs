# Design: Experiment 35 Reproducible Local RAG Benchmark

## Status

DRAFT. Measured execution must not begin until the protocol and plan are committed (Confirmatory) and the pipeline sweep has passed.

Source of the agreed decisions: `docs/proposals/first-publication-benchmark.md` (Draft 1, 27 October 2026). Where that document and an earlier version of this change disagree, that document wins.

## Context

The first version of this change planned two small local baselines on the operator's Mac: 35A (FinanceBench subset, `documents` profile) and 35B (RepoProbe answers and FreshStack retrieval, `codebase` profile). Larger runs were to move to a later cloud proposal.

Two things changed on 27 October 2026:

- ADR-103 made llama.cpp with a public GGUF file the only local runtime for experiment evidence. It added the `publication` purpose, which must be Confirmatory and must pin its runtime in `plan.json`.
- The first fellowship paper needs a citable benchmark. The carry-forward review (`openspec/changes/archive/2026-10-27-reproducible-experiment-runtime/carry-forward.md`) chose Experiments 2, 3, 10b, 15, 22 and 25 to go forward as arms of one new `publication` experiment, not as single re-runs.

Experiment 35 becomes that experiment.

## Goals

- Measure the full OMRS pipeline on three public datasets from three domains, with gold labels.
- Measure what four pipeline choices change, one at a time, against one baseline.
- Make every number repeatable by another group on another machine: pinned GGUF files, pinned build, stated tolerance.
- Report uncertainty for every number, and paired comparisons for every arm.
- Release what the licences allow, in a form a Software Tool Article can use.

## Non-Goals

- No production default changes from this experiment. A finding that suggests one goes to a separate proposal.
- No comparison with LlamaIndex, Haystack, LangChain or other frameworks.
- No RepoProbe answer scoring. It moves to a later paper (see "RepoProbe moved out").
- No Ragas, OpenTelemetry or other evaluation tooling in the base runtime dependency path.
- No decision here on local or cloud hardware. The timing in task 1.4 informs it.

## D1. Purpose, size and runtime

- `experiment.json`: `purpose: publication`, `size: Confirmatory`, `category: retrieval`.
- Commit `protocol.md` and `plan.json` before the first measured run. After that, a change goes only into the `amendments` list.
- `plan.json` holds the ADR-103 `runtime` block:
  - `runtime_under_test: false`.
  - `models[]`: one entry per local model (embedding 0.6B, 4B, 8B; answer model; Ragas judge when local). Each entry names `role`, `repository`, `file`, `sha256`, `runtime: llama.cpp`, `build` and `server_args`.
  - `references[]`: each hosted model, with provider and model id.
  - `tolerance[]`: the largest change in each primary metric that still counts as the same result on another back end (Metal, CUDA, CPU).
- Embedding files come from the public `Qwen/Qwen3-Embedding-0.6B-GGUF`, `Qwen/Qwen3-Embedding-4B-GGUF` and `Qwen/Qwen3-Embedding-8B-GGUF` repositories. Use the same quantisation for all three sizes (Q8_0 unless the freeze records a reason for another).
- Before the first score of each run, call `verify_llamacpp_runtime` from `experiments/_lib/llamacpp_runtime.py`. A wrong build or file hash stops the run. Pass `runtime=found.as_run_record()` to `record_run_start`.
- Models llama.cpp cannot run (the ONNX reranker, OCR engines) stay under the existing runtime-manifest record: name, revision and file hash.
- Hosted models appear only as named reference arms.

## D2. Datasets

### FinanceBench (open sample)

- All 150 questions. Ingest the real source PDFs through the full document path: reader, OCR routing, Markdown interface, chunking, embedding, LanceDB.
- A run that starts from pre-extracted text does not count as the primary result. It may be reported as a diagnostic.
- Hit rule: a retrieved chunk is a hit when its source is the gold `evidence_doc_name` and its page is the gold page. `evidence_page_num` is zero-indexed. One function converts it to the page numbering that OMRS stores, with a unit test on a known page. A chunk that spans pages is a hit when any of its pages is the gold page. A question with several evidence entries is a hit at K when any gold page is hit within the top K.
- Licence CC BY-NC 4.0. Keep the PDFs and derived text out of git and out of any CC BY release.

### FreshStack, LangChain slice

- The slice exported by `prepare_freshstack.py` with seed 20260530: about 10,024 parent documents, all 223 queries, the qrels of Experiments 9a and 22. Indexing is the main cost; a smaller query set only widens the intervals.
- Build a new index for each arm. Experiment 22 does not count as a baseline. It used default chunking (32,631 chunks), `qwen/qwen3-embedding-4b` through OpenRouter, hybrid RRF k=60, rerank off and top_k 50. Report it beside the result as a reference and name the settings that differ. Experiment 9a used one vector per parent document, so its numbers are not comparable.
- Map each retrieved chunk to its parent document and keep only the first rank of each parent before scoring, as Experiment 22's `run_eval.py` does. Reuse that mapping code.
- Licence CC BY-SA 4.0. Release derived files under CC BY-SA.

### BioASQ (`enelpol/rag-mini-bioasq`, test split)

- 707 questions over 40.2K PubMed abstracts, with gold passage IDs and reference answers. A hit is a retrieved chunk whose passage ID is a gold passage ID.
- Licence CC BY 2.5.
- If indexing 40.2K abstracts does not fit the time budget, subset by question type and freeze the subset before scoring (proposal risk table).
- Fallback: NFCorpus (`BeIR/nfcorpus`), retrieval scores only, no Ragas. Use it only when BioASQ cannot be used. Check its academic-use terms first.

### RepoProbe moved out

RepoProbe (old 35B-1) moves to a later paper. It labels no gold files or chunks, so it gives no retrieval metric, and every score needs a hosted LLM judge. The scoring notes decided on 2026-10-23 stay valid for that later paper: call `SimpleScorer.score_answer_multiple` directly at a pinned RepoProbe commit; judge `glm-5.3` through Z.AI at `reasoning_effort: low` with `num_iterations=3`; optional 5-question check with a second judge; label the result "single-shot RAG on RepoProbe" and never compare it with the agent scores in the RepoProbe paper.

## D3. Arms

All arms run on the same questions. Each ablation changes one component against the baseline.

| Arm | What changes | Past evidence it carries forward |
|---|---|---|
| Baseline | `documents` profile defaults, Qwen3-Embedding-4B (local GGUF) | Experiment 3 (end-to-end); Experiment 22 used 4B through OpenRouter |
| Embedding 0.6B | 0.6B in place of 4B | Experiments 2 and 22 |
| Embedding 8B | 8B in place of 4B | Experiment 2 (0.6B and 8B tied on an easy 17-query set) |
| Reranker off | Reranker off against the baseline's on | Experiments 10b and 15 (the reranker hurt technical retrieval) |
| Token-aware chunking off | Model-token Markdown chunking (ADR-063) off against on | Experiment 25 |

Notes:

- The `documents` profile is the baseline on all three datasets, FreshStack included. The earlier plan used the `codebase` profile for FreshStack. The proposal replaces that.
- The 8B arm runs on all three datasets, so the three sizes are compared on equal terms. The paper claims only what this arm shows.
- The `documents` profile sets `rerank_enabled: true`, so the reranker arm turns it off.
- Token-aware chunking is on when `EMBEDDING__TOKENIZER_MODEL` and its revision resolve (ADR-063). The off arm leaves them unset, so the legacy Markdown path runs. Before freeze, check which documents of each dataset route through the Markdown splitter. If the arm changes no chunk on a dataset, record the cell as "not applicable" and do not run it. BioASQ abstracts are short and may be such a case.
- Each arm uses the arm's own embedding model for the tokenizer. The Qwen3 embedding family shares one tokenizer.
- Answers come from one pinned answer model for all arms, through llama.cpp. The freeze names it.

## D4. Metrics

### Primary (gold labels, no judge)

- Recall@10, MRR@10, nDCG@10 (binary relevance from the gold labels).
- Hit@page (FinanceBench only), with the D2 hit rule.
- Primary endpoint for the arm comparisons: nDCG@10. Holm correction applies to it. The other primary metrics are reported with intervals and paired differences, without a Holm claim.

### Secondary (LLM judge)

- Ragas 0.4.3: faithfulness, answer relevancy, context precision, context recall.
- Pin the Ragas version, the judge model and its settings, temperature 0. Run the judge through llama.cpp when possible.
- A metric that needs a reference answer runs only where the dataset has one (FinanceBench, BioASQ). Check FreshStack at freeze. Otherwise report "not measured".
- Check about 50 judged items by hand. Define the agreement measure in the protocol before the check. Report the agreement.
- Ragas never replaces a primary metric. When a Ragas score improves and a primary metric worsens, report both.

### Latency and diagnostics

- Latency per query: p50 and p95, without warm-up. Measured runs do not run in parallel on one machine.
- Diagnostics: evidence recovery after parsing and OCR, evidence kept after chunking, ingestion time, OCR work and failures, chunk count, embedding tokens, index size.

## D5. Repetitions

- Each arm runs 3 times.
- Each arm builds its index once. Runs 2 and 3 repeat retrieval, answers, the Ragas judge and timing on that index. With a fixed index, runs 2 and 3 must retrieve exactly what run 1 retrieved. This is the determinism check, and the report states its result.
- Rebuild check: for each dataset, rebuild the 4B baseline index once in a fresh process and compare the retrieved lists with run 1. This shows whether index building is repeatable. A full rebuild for every run of every arm would cost many hours and add nothing to the statistics, because retrieval on a fixed index does not vary.
- Embedding mode: exact or fast, as the pipeline sweep's Part C decides. The plan states the mode and its tolerance.
- Run 1 gives the scored retrieval result. A mismatch is a finding: record it, report the run-to-run difference, and do not swap in another run.
- The 3 runs measure the stages that can change: the generated answer, the Ragas judge and latency. The rebuild check covers index building. Report the run-to-run standard deviation for each.
- Tests compare arms question by question. Average the 3 runs for each question first.

## D6. Statistics (basic set)

For each dataset and arm:

1. Mean with a 95% confidence interval: bootstrap over questions for scores, Wilson for hit rates.
2. Difference from the baseline with a paired 95% confidence interval. This is the main number.
3. One paired test per comparison: permutation test for scores, McNemar's exact test for hit or miss.
4. Holm correction across the arms of one dataset.
5. Wins, losses and ties per question.
6. The minimum detectable effect, stated in the protocol before the run: about 4 points at 150 to 223 questions, about 2 points at 707.

Code: reuse `wilson`, `win_loss`, `mcnemar_exact`, `paired_permutation`, `paired_bootstrap`, `holm` and `min_detectable_effect` from `.agents/skills/s-experiment/references/stats.py`, and `paired_bootstrap_ci` and `cell_record` from `experiments/_lib/stats.py`. If the skill file cannot be imported from the experiment, copy the functions unchanged into `experiments/_lib/stats.py` with their tests. Do not write new statistics code. Add plain nDCG@10 and hit@page to `experiments/_lib/retrieval_metrics.py` without changing the existing definitions.

Hypotheses (one per ablation arm and dataset): H0, the arm's nDCG@10 equals the baseline's. H1, it differs. Decision rule: a difference counts when the Holm-adjusted p is below 0.05 and the paired interval excludes zero. Otherwise report "no difference larger than the minimum detectable effect was found".

One table per dataset:

| Arm | n | Recall@10 [CI] | MRR@10 [CI] | nDCG@10 [CI] | Hit@page % [CI] | Δ nDCG@10 [paired CI] | p (Holm) | W/L/T | Faithfulness ± run SD | Answer relevancy ± SD | Context P / R ± SD | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## D7. Hardware and timing

- Task 1.4 times local 0.6B, 4B and 8B embedding on a fixed slice of each corpus. It records wall time, tokens and peak memory, and extrapolates to each full corpus. The timing is a planning measurement, not a scored run.
- The change `pipeline-sweep-llamacpp` plans the same timing. If its numbers exist for the measurement machine and the pinned files, Experiment 35 reuses them and records the source.
- Fallback: if local 4B does not fit the time budget, the reference arm becomes OpenRouter `qwen/qwen3-embedding-4b`, named as hosted (ADR-103).
- The run may be local (the 64 GB M5 Pro MacBook Pro) or on rented cloud hardware. The operator decides after the timing. Either way: the same GGUF files, the same build, and the D1 tolerance. Run all arms of one dataset on the same machine and back end, so the paired comparisons stay fair.
- Record the hardware (chip or GPU, memory, back end) in every run record.

## D8. Observability

The harness writes one secret-free JSONL trace per query and major stage, outside the MCP stdout channel. Minimum fields:

- benchmark revision, run ID, arm, repetition number;
- dataset and question ID;
- effective settings and model identities (file hash for local models);
- reader and OCR route where applicable;
- chunk counts;
- retrieved chunk IDs, parent or page IDs and scores;
- reranker input and output ranking where applicable;
- stage durations and token counts where available;
- answer model identity, judge identity;
- error or degraded status.

Failed documents and questions stay in the denominators. The schema stays simple enough to map to OpenTelemetry later. Experiment 35 adds no OpenTelemetry dependency.

## D9. Ragas isolation

Ragas goes in a separate `uv` dependency group (for example `eval`), not in a published extra. The pinned version is 0.4.3 (Apache-2.0). It pulls in `langchain`, `datasets` and `tiktoken`. Before adding it, run a dry resolve and check whether `tests/test_dependency_floors.py` needs an exemption. When Ragas is missing, the primary metrics still run and Ragas metrics are reported as not measured.

## D10. Publication rules that change the experiment

1. A small shareable example set: example input, expected output and a short guide to reading it (Software Tool Article). Use only data whose licence allows sharing, for example a few BioASQ items with attribution.
2. Split `output/` into `output/shareable/` and `output/restricted/`. Restricted holds anything with corpus text or FinanceBench-derived content.
3. Licences: FinanceBench CC BY-NC (never released under CC BY); FreshStack CC BY-SA (derived files under CC BY-SA); BioASQ CC BY 2.5. Publish scores, question IDs and rebuild scripts. Do not publish corpus text.
4. Archive code and shareable outputs on Zenodo with a DOI. Give each dataset's derived files their own archive with their own licence.
5. Before the repository or any release goes public, remove names and home-folder paths, and search the upload for them.
6. `output/` stays out of git. Copy it to `DATA/omrs/experiments/` with SHA-256 checksums before any worktree removal.

## Validity controls

- Freeze dataset revisions, question IDs, gold labels, source file hashes and query order.
- Freeze the FinanceBench page conversion and its test.
- Freeze effective OMRS settings per arm and the `runtime` block.
- Freeze scoring code, metric definitions, the statistics plan and the minimum detectable effect.
- Record the OMRS commit and dependency-lock hashes in each run record.
- Preserve failures in denominators.
- Do not tune on measured outcomes.

## Open questions (resolve at freeze)

1. Which answer model and which Ragas judge model, and can the judge run through llama.cpp?
2. What wall-time, memory and paid-provider budget applies, and does the run go local or to rented cloud hardware?
3. Does BioASQ fit in full, or is a question-type subset needed?
4. Does FreshStack carry reference answers that Ragas context recall can use?
5. Does the token-aware chunking arm change any chunk on BioASQ?

Resolved on 2026-10-27 by the publication proposal: datasets and sizes, the baseline and arms, metrics, repetitions, statistics, and RepoProbe moved out.

## Risks

| Risk | Response |
|---|---|
| Small differences between llama.cpp back ends | `tolerance[]` per primary metric (ADR-103) |
| The Ragas judge disagrees with people | Report hand-check agreement; Ragas stays secondary |
| Indexing 40K abstracts takes too long | Time first; subset BioASQ by question type before scoring |
| The reranker result changes on llama.cpp embeddings | Report it as found; a negative result is still a result |
