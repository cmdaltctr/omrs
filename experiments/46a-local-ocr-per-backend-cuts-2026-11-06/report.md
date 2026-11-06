# Experiment 46a: Per-backend confidence cuts for local OCR

- **Folder**: `46a-local-ocr-per-backend-cuts-2026-11-06`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Follow-up of**: [Experiment 46](../46-local-ocr-backends-2026-11-04/report.md). This folder runs no OCR. It re-reads the saved Experiment 46 output.
- **Operator**: OMRS maintainer, coding agent
- **Evidence file**: `output/cut_sweep.json` is the record's evidence file. It holds counts and hashes only and stays in git. Every number below comes from it.

## Answer

- **Question**: Which default confidence cut should each local OCR backend use, so that few kept pages are bad?
- **Answer**: Two different cuts. PP-OCRv6 small passes the 5% limit from 0.91 upward (0.92: 48 pages kept, 2 bad, 4.2%). Indra passes from 0.88 upward, but only a cut of 0.94 or higher keeps no bad page (0.94: 97 pages kept, 0 bad).
- **Decision**: Set the defaults to 0.92 for PP-OCRv6 small and 0.94 for Indra. Today both use 0.90. In the chain (PP-OCRv6 small, then Indra), this keeps 108 pages local with 2 bad. PP-OCRv6 small alone at 0.90 keeps 56 pages local with 3 bad.
- **How sure**: Low to medium. The sample is 229 pages from 9 documents, and the 0.90 against 0.92 difference for PP-OCRv6 small is one bad page.
- **Next step**: Apply the defaults in the `local-ocr-per-backend-cuts` change. A larger sample can move either default later.

## Plan (written before the run)

- **Question**: Which confidence cut should each local OCR backend use as its default, so that few kept pages are bad?
- **Decision**: Set the default cut of PP-OCRv6 small and of Indra in the `local-ocr-per-backend-cuts` change. Today both use one shared cut of 0.90.
- **Limit**: A cut qualifies when at most 5% of the pages it keeps are bad. Each backend is judged on its own, with no script filter.
- **Bad page**: a kept page whose token recall against the reference text is below 0.5. This is the Experiment 39 and Experiment 46 definition.
- **When the limit was chosen**: after the data was seen. The 5% bound comes from Experiment 46's plan. Applying it to each backend alone, and choosing the defaults, happened after the operator read the saved results. This record is a setting choice, not a test of a hypothesis fixed in advance. That is why the status is `MEASURED` and not `PASS`.
- **Data**: the 229 pages of Experiment 46. PP-OCRv6 small uses the stored Experiment 33 rows. Indra uses arm B.
- **Cuts**: 0.85 to 0.97 in steps of 0.01.
- **Arms**: PP-OCRv6 small alone; Indra alone; the chain, where PP-OCRv6 small keeps pages at its cut and Indra at 0.94 reads the rest.
- **Rules reused unchanged**: the row loader, the token recall rule and the bad-page rule are imported from Experiment 46 (`summarise.py` and `run_arm.py`). A page is kept when its confidence is at least the cut. A page with no confidence is never kept.
- **Run**: `uv run --no-sync python experiments/46a-local-ocr-per-backend-cuts-2026-11-06/analysis.py --source <Experiment 46 output folder>`

## Results

Source for every table: `output/cut_sweep.json`. "Bad share" is bad pages divided by kept pages.

PP-OCRv6 small alone (`pp_ocrv6_small_alone`). All kept pages are Latin, and so are all bad pages.

| Cut | Kept | Bad | Bad share |
| --- | ---: | ---: | ---: |
| 0.85 | 63 | 5 | 7.9% |
| 0.90 (today) | 56 | 3 | 5.4% |
| 0.91 | 53 | 2 | 3.8% |
| **0.92** | **48** | **2** | **4.2%** |
| 0.94 | 35 | 2 | 5.7% |
| 0.96 | 23 | 0 | 0% |

Indra alone, no script filter (`indra_alone`).

| Cut | Kept | Bad | Where the bad pages are |
| --- | ---: | ---: | --- |
| 0.85 | 186 | 15 (8.1%) | Bengali 9, Latin print 6 |
| 0.90 | 138 | 6 (4.3%) | all Latin print (`io04`) |
| 0.92 | 117 | 3 | Latin |
| **0.94** | **97** | **0** | none |
| 0.95 / 0.96 / 0.97 | 83 / 64 / 54 | 0 | none |

Chain: PP-OCRv6 small at its cut, then Indra at 0.94 on the rest (`chain_pp_then_indra`).

| PP-OCRv6 small cut | Kept local | Bad | Bad share |
| --- | ---: | ---: | ---: |
| 0.90 | 110 | 3 | 2.7% |
| **0.92** | **108** | **2** | **1.9%** |
| 0.94 | 106 | 2 | 1.9% |

How the defaults were chosen. Each backend can be listed alone, so each cut must meet the limit alone.
- **PP-OCRv6 small:** on the 0.01 grid, 0.91 also passes the 5% limit (53 kept, 2 bad, 3.8%). A cut of 0.92 keeps the same 2 bad pages (one print page of `io04`, one handwriting page of `rf07`) with 5 fewer kept pages. The operator chose 0.92 on 2026-11-06 from the coarser table.
- **Indra:** 0.88 to 0.90 are under the limit, but all 6 bad pages at 0.90 are Latin print pages. The old script filter hid them. A cut of 0.94 is the lowest with no bad page, at a cost of 41 pages against 0.90. The operator chose 0.94 on 2026-11-06.
- **Chain:** PP-OCRv6 small at 0.92 and Indra at 0.94 keep 52 more pages local than PP-OCRv6 small alone at 0.90 (108 against 56).

This is a setting choice, not a publication result.

## Limits

1. 229 pages from 9 documents: four non-Latin documents (Arabic `io02`, `io03`, Devanagari `io01`, Bengali `io07`) and five Latin documents.
2. The reference text comes from a vision model, not a person. Recall measures agreement with it.
3. The difference between 0.90 and 0.92 for PP-OCRv6 small is one bad page (3 against 2). A different sample could move it.
4. The 5% limit was applied per backend after the data was seen, so the result is a setting choice and not a test.
5. The chain table fixes Indra at 0.94 and does not sweep it.

## Artefacts and checksums

| File | SHA-256 |
| --- | --- |
| `analysis.py` | `3c99344468efdd7b00bf6d9f2e57bf9f15854e7c1077ab33c67444843dcab2aa` |
| `output/cut_sweep.json` | `c83db1e5adcb75c725faac0dc17d80e09dad1b371d9bbccce8c3e8d52c4c7664` |
| Input `pages.json` (Experiment 46) | `e1fd1862df29f81207f52fa62ad1791691bc3c80460ac20634dba9abd18328f0` |
| Input `arm_b.jsonl` (Experiment 46 output) | `fb464318440440c8b7d0c246910a92e45d1723df6e783f57bd36569046a85f37` |
| Input Experiment 33 `local_ocr/pages.json` | `e6223d1536293b6860cd8eda9d48b2e383139e3e6c2f5e095a36f2b9822a711f` |
