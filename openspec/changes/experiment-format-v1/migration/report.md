# Move report: experiment format v1

Date: 2026-10-25. Folders: 50. Index rows without a folder: 1.

Each line lists the judgements the move made for one folder. The original status text is kept in
`migration.from_status` in each `experiment.json`.

| Folder | Status | Notes |
|---|---|---|
| `1-reranker-threshold-calibration-2026-05-12` | PASS | category `retrieval`, size `None` |
| `2-embedding-model-comparison-2026-05-19` | PASS | category `retrieval`, size `None` |
| `3-e2e-smoke-test-metadata-2026-05-20` | PASS | category `ingestion`, size `None` |
| `4-async-chunking-responsiveness-2026-05-27` | PASS | category `runtime`, size `None` |
| `5-reranker-pool-sizing-2026-05-27` | PASS | category `retrieval`, size `None` |
| `5b-persistent-mps-reranker-worker-2026-08-20` | FAIL | no index row; status, title and finding taken from the folder; status `results.md: **Overall verdict:** **FAIL — promotion rejected; ONNX CPU remains the production default**` mapped to `FAIL`; category `runtime`, size `Standard` |
| `6-markdown-chunking-quality-2026-05-27` | INCONCLUSIVE | status `PARTIAL` mapped to `INCONCLUSIVE`; category `retrieval`, size `None` |
| `6b-qasper-markdown-chunking-2026-05-28` | FAIL | no index row; status, title and finding taken from the folder; status `results.md: **Status**: COMPLETE (real negative result)` mapped to `FAIL`; category `retrieval`, size `None` |
| `6c-markdown-chunking-quickwins-2026-05-28` | PASS | no index row; status, title and finding taken from the folder; status `results.md: **Status**: PASS` mapped to `PASS`; category `retrieval`, size `None` |
| `7-chunk-overlap-sensitivity-2026-05-27` | PASS | category `retrieval`, size `None` |
| `7a-chunk-overlap-evidence-2026-05-29` | INCONCLUSIVE | category `retrieval`, size `None` |
| `8-query-embedding-cache-2026-05-27` | PASS | category `runtime`, size `None` |
| `8a-query-embedding-cache-fullsize-2026-05-29` | PASS | category `runtime`, size `None` |
| `9-hybrid-retrieval-2026-05-27` | INCONCLUSIVE | index date 2026-05-30 differs from folder date 2026-05-27; folder date kept; status `PARTIAL` mapped to `INCONCLUSIVE`; category `retrieval`, size `None` |
| `9a-hybrid-retrieval-freshstack-langchain-2026-05-30` | FAIL | index date 2026-05-31 differs from folder date 2026-05-30; folder date kept; category `retrieval`, size `None` |
| `9a-rerun-post-adr021-reranker-2026-06-29` | SUPERSEDED | status `SUPERSEDED by D17` mapped to `SUPERSEDED`; superseded_by `10b-reranker-pool-size-corrected-2026-06-29`; category `retrieval`, size `None` |
| `10-reranker-technical-workload-calibration-2026-05-31` | FAIL | status `FAIL / INCONCLUSIVE` mapped to `FAIL`; category `retrieval`, size `None` |
| `10.1-doc-similarity-threshold-calibration-2026-06-29` | PASS | index date 2026-07-16 differs from folder date 2026-06-29; folder date kept; category `graph`, size `None` |
| `10b-reranker-pool-size-corrected-2026-06-29` | ACTIVE | status `REBUILT — Stage 6 pending` mapped to `ACTIVE`; category `retrieval`, size `Standard` |
| `11-liteparse-pdf-quality-2026-06-20` | INCONCLUSIVE | status `PARTIAL` mapped to `INCONCLUSIVE`; category `ingestion`, size `None` |
| `12-hybrid-default-promotion-2026-06-29` | SUPERSEDED | status `SUPERSEDED by D17` mapped to `SUPERSEDED`; superseded_by `10b-reranker-pool-size-corrected-2026-06-29`; category `retrieval`, size `None` |
| `13-hard-technical-threshold-calibration-2026-06-29` | ACTIVE | status `REBUILT — Stage 6 pending` mapped to `ACTIVE`; category `retrieval`, size `Standard` |
| `14-liteparse-qasper-promotion-2026-06-29` | ACTIVE | status `REBUILT — Stage 6 pending` mapped to `ACTIVE`; category `ingestion`, size `Standard` |
| `15-gte-reranker-swap-2026-07-31` | INCONCLUSIVE | no index row; status, title and finding taken from the folder; status `results.md: **Status:** INCONCLUSIVE (small sample + reduced candidate pool; see caveats)` mapped to `INCONCLUSIVE`; category `retrieval`, size `None` |
| `16-reranker-coreml-fp16-2026-08-03` | FAIL | category `runtime`, size `None` |
| `17-reranker-mps-vs-onnx-cpu-2026-08-11` | FAIL | category `runtime`, size `None` |
| `18-ingestion-lock-scope-ab-2026-08-19` | PASS | category `runtime`, size `Standard` |
| `19-lancedb-lifecycle-qualification-2026-08-21` | PASS | no index row; status, title and finding taken from the folder; status `results.md: ## Verdict **PASS** (run2, 14/14 gates)` mapped to `PASS`; category `runtime`, size `Standard` |
| `19-native-fts-vs-bm25-sparse-2026-08-29` | FAIL | status `FAIL (promotion gates)` mapped to `FAIL`; category `retrieval`, size `None` |
| `20-citation-faithfulness-2026-09-02` | PASS | category `generation`, size `None` |
| `21-lancedb-literal-faithfulness-2026-09-02` | PASS | category `runtime`, size `None` |
| `22-raw-query-qwen4b-baseline-2026-09-07` | MEASURED | status `COMPLETE (measurement)` mapped to `MEASURED`; category `retrieval`, size `Standard` |
| `23-ocr-routing-gate-calibration-2026-09-07` | MEASURED | status `COMPLETE` mapped to `MEASURED`; category `ingestion`, size `Quick` |
| `24-ocr-routing-eval-2026-09-08` | PASS | status `PASS (run 2)` mapped to `PASS`; category `ingestion`, size `Standard` |
| `25-token-chunking-ablation-2026-09-08` | PASS | category `retrieval`, size `Standard` |
| `26-query-instruction-ablation-2026-09-08` | FAIL | index date 2026-09-09 differs from folder date 2026-09-08; folder date kept; status `FAIL (negative result)` mapped to `FAIL`; category `retrieval`, size `Standard` |
| `27-combined-candidate-path-2026-09-09` | FAIL | status `FAIL (negative result)` mapped to `FAIL`; category `retrieval`, size `Standard` |
| `28-pdf-classification-prevalence-2026-09-09` | FAIL | status `FAIL (negative result)` mapped to `FAIL`; category `ingestion`, size `Standard` |
| `29-pdf-routing-repeat-2026-09-13` | PASS | status `PASS (recall gate not_evaluable by construction; dev_003 label amended)` mapped to `PASS`; category `ingestion`, size `Standard` |
| `30-reader-fallback-chain-2026-09-13` | PASS | status `PASS (4/4 gates)` mapped to `PASS`; category `ingestion`, size `None` |
| `31-reader-rescue-retrieval-impact-2026-09-15` | PASS | status `PASS (decisive; negative for the candidate)` mapped to `PASS`; category `ingestion`, size `None` |
| `32-misnamed-extension-detection-2026-09-16` | PASS | status `PASS (5/5 gates)` mapped to `PASS`; category `ingestion`, size `None` |
| `33-ocr-routing-natural-positive-2026-09-17` | FAIL | status `FAIL (Stage A)` mapped to `FAIL`; category `ingestion`, size `Standard` |
| `34-worker-sample-review-2026-09-19` | PASS | index date 2026-09-24 differs from folder date 2026-09-19; folder date kept; status `PASS (scoped to 4 pages)` mapped to `PASS`; category `review`, size `None` |
| `36-reader-output-normalisation-2026-09-25` | PASS | category `ingestion`, size `None` |
| `37-dots-mocr-routing-acceptance-2026-09-30` | PASS | category `ingestion`, size `Standard` |
| `38-rescue-quality-signal-2026-09-30` | FAIL | index date 2026-10-07 differs from folder date 2026-09-30; folder date kept; category `ingestion`, size `Standard` |
| `39-local-tier-escalation-2026-09-30` | FAIL | index date 2026-10-06 differs from folder date 2026-09-30; folder date kept; category `ingestion`, size `Standard` |
| `42-clef-flash-confirmation-2026-10-08` | FAIL | index date 2026-10-09 differs from folder date 2026-10-08; folder date kept; category `ingestion`, size `Standard` |
| `leiden-vs-louvain-2026-08-14` | MEASURED | no index row; status, title and finding taken from the folder; status `ADR-044 section Experiment (no status recorded; a comparison without a gate)` mapped to `MEASURED`; category `graph`, size `Quick` |

## Index rows without a folder

- `| 35       | Local profile baselines (draft change, no folder yet: [`openspec/changes/experiment-35-full-document-rag-benchmark`](../openspec/changes/experiment`

These become entries in `experiments/reserved.json`.
## Needs your review

These calls were made by the move. Each one is a one-line change in that folder's `experiment.json`.

1. `10-reranker-technical-workload-calibration-2026-05-31`: the index says `FAIL / INCONCLUSIVE`. The move kept `FAIL`. Its pool-size gates are invalid (results.md line 180 onwards), and `10b` says it supersedes Experiment 10 for that question. The reranker finding still stands and backs the `RERANK_ENABLED=false` default, so the move did not mark it `SUPERSEDED`.
2. `PARTIAL` became `INCONCLUSIVE` for 6, 9 and 11. Experiment 11 had mixed hypotheses (H1 and H4 passed, H2 and H3 failed), and LiteParse was still adopted.
3. `REBUILT — Stage 6 pending` became `ACTIVE` for 10b, 13 and 14, because their campaign cells have not run.
4. `COMPLETE` became `MEASURED` for 22 and 23: a baseline and a calibration sweep with no pass or fail gate.
5. `6b` had no index row. Its results say `COMPLETE` with a negative result, so the move set `FAIL`.
6. `leiden-vs-louvain-2026-08-14` had no status anywhere. Its result is in ADR-044. The move set `MEASURED` and `refs.adrs = ["ADR-044"]`.
7. Six folders had no index row: 15, 19 (LanceDB lifecycle), 5b, 6b, 6c and leiden-vs-louvain. Their titles and findings were written from their own results files.
8. Eight index dates differ from the folder date (10.1, 26, 34, 38, 39, 42, 9, 9a). The record keeps the folder date, which is the planning date. The index now shows that date.
9. Size is empty for folders that have only one of `protocol.md` and `plan.json`. The checker reports this as information.

## Check after the move

`uv run --no-sync omrs experiments check experiments` on 2026-10-25, after the index was written:

- Errors: 0
- Warnings: 4, all `number-shared` (two folders each for `19` and `9a`)
- Information: 30 `size-missing`, 14 `files-missing`

The index rebuild kept all 44 linked rows with the same title and finding. Experiment 35 moved to the reserved-numbers table. Six rows were added (15, 19 LanceDB lifecycle, 5b, 6b, 6c, leiden-vs-louvain). Eight dates changed to the folder date (item 8 above). The old status qualifiers, such as "PASS (scoped to 4 pages)", are no longer in the index, but each record keeps them in `migration.from_status`.
