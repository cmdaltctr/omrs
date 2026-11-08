# Experiment 48: Pipeline sweep on llama.cpp

- **Folder**: `48-pipeline-sweep-llamacpp-2026-11-01` (numbered 43 until 2026-11-07, amendment A2)
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-11-08
- **Operator**: Aizat, with the orchestrator agent.
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: the per-stage JSONL files in `output/` and `output/g3-rerun/`. `output/summary.json` collects them; it was written by hand from those files (no script) and was rechecked by an independent review.

## Answer

- **Question**: Does every OMRS pipeline stage run without error when every local model runs on llama.cpp with public GGUF files, and at what rate do the 0.6B, 4B and 8B Qwen3-Embedding models embed?
- **Answer**: Yes. All three gates pass: 0 stage errors; 0.6B 16/17 (MRR 0.971), 8B 17/17 (MRR 1.000), 4B with reranker 16/17 (MRR 0.941); and a G3 rerun on a fresh pod repeated all 168 searches (1,173 real chunk ids) with 0 ranking changes. The first G3 attempt was void (D3); the rerun replaces it.
- **Decision**: Experiment 35a may freeze its plan on this runtime, in exact mode. Fast mode is refused.
- **How sure**: Medium. The fixed set is small (17 questions, 11 documents) and sits near its ceiling.
- **Next step**: Size the Experiment 35a pod for CPU, not GPU, and fix the single-core chunker first.

## What we tested

The full OMRS pipeline on OMRS's managed llama.cpp router (build b11941, CUDA), against the earlier Ollama results of Experiments 2 and 3. It informs the freeze of Experiment 35a. Data: Experiment 3's 6 documents, 5 FinanceBench PDFs (568 pages), 17 questions plus 25 FinanceBench questions, and 200-item timing slices of FreshStack and BioASQ.

## Results

Every gate passes.

| Gate | Pass when | Result | Gate |
| --- | --- | --- | :---: |
| G1 | Zero errors in every stage and mode | 0 errors: 11 ingests, 168 searches, 42 answers, 42 claim-checked answers | PASS |
| G2 | 0.6B and 8B dense at least 16/17 and MRR at least 0.94; 4B with reranker at least 16/17 | 0.6B 16/17, 0.971 (Exp 2 Ollama: 17/17, 1.000); 8B 17/17, 1.000 (Exp 2: 17/17, 1.000); 4B dense + reranker 16/17, 0.941 (Exp 3: 17/17). Files: `output/arms-*.jsonl`, `output/search.jsonl` | PASS |
| G3 | Identical rankings on a repeat in a new process | Rerun 2026-11-08 (D9): 168 searches, 1,173 result ids (302 distinct chunks, 0 blank), 0 mismatches. First attempt void (D3) | PASS |

4B search modes on the 17 questions (reported only, `output/search.jsonl`): dense 15/17 (MRR 0.902), dense + reranker 16/17 (0.941), hybrid 15/17 (0.926), hybrid + reranker 16/17 (0.941).

FinanceBench, 25 questions, 4B (reported only, no earlier number; `output/search.jsonl`): document Hit@1 and Hit@page are dense 24 and 18, dense + reranker 22 and 16, hybrid 24 and 19, hybrid + reranker 21 and 16. Recall@10 was not computed (D10).

### Part B: embedding timing on one RTX 4090

| Model | Slice | Files | Tokens | Embedding s | Read and chunk s | Wall s | Tokens/s | Peak GPU MB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4B | FreshStack | 200 | 264,317 | 21.1 | 72.7 | 270.0 | 12,527 | 7,390 |
| 4B | BioASQ | 200 | 50,784 | 6.7 | 0.6 | 182.4 | 7,625 | 7,390 |
| 4B | FinanceBench | 5 | 415,929 | 26.3 | 360.8 | 392.8 | 15,814 | 7,390 |
| 8B | FreshStack | 200 | 264,317 | 29.9 | 73.8 | 280.7 | 8,846 | 11,618 |
| 8B | BioASQ | 200 | 50,784 | 8.5 | 0.6 | 184.8 | 5,966 | 11,618 |
| 8B | FinanceBench | 5 | 415,929 | 40.0 | 358.3 | 404.8 | 10,392 | 11,618 |
| 0.6B | FreshStack | 200 | 264,317 | 10.7 | 74.4 | 258.7 | 24,741 | 2,617 |
| 0.6B | BioASQ | 200 | 50,784 | 4.1 | 0.6 | 178.2 | 12,384 | 2,617 |
| 0.6B | FinanceBench | 5 | 415,929 | 9.9 | 359.2 | 374.1 | 42,223 | 2,617 |

Each row is its own GPU peak; the three slices of one model give the same value. "Read and chunk" is the reader and chunker time OMRS reports. The rest of the wall time is about 0.88 s per file on FreshStack and BioASQ (for example 176 of 270 s for 4B on FreshStack), spent neither embedding nor chunking. It is probably the per-file cost of calling `ingest_path_async` once per file in this harness; this run does not show which part. All rows are in `output/timing-*.jsonl`.

### Part C: fast mode against exact mode (4B)

Lowest cosine: FreshStack 0.99895, BioASQ 0.99970, FinanceBench 0.99948. The rule needs at least 0.9999, so fast mode is **not** allowed.

Top-10 rankings, recomputed on the Mac from the saved vectors (D4): each chunk is a query against the other chunks of its slice. The top-10 order changed for 324 of 529 FreshStack chunks (set changed 90, top-1 changed 19), 108 of 215 BioASQ (27, 4) and 319 of 662 FinanceBench (85, 30). Of these, 23 FreshStack and 23 FinanceBench rows only swap chunks whose exact vectors are identical (a tie the sort orders by id). Fast mode fails the ranking rule too. Chunk-to-chunk neighbours are often near ties, so this measure overstates the change a real query would see. No speed for either mode was recorded (D5).

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary) | A stage errors, or Hit@1 or MRR falls below the bounds | Supported: G1 to G3 pass | The llama.cpp pipeline matches the Ollama results within one question |

### Amendments and deviations

- A1 (2026-11-01): metadata extraction disabled in every stage.
- A2 (2026-11-07): renumbered 43 to 48.
- A3 (2026-11-07): OMRS-managed router; one RunPod RTX 4090 pod, b11941 `cuda` flavour.
- **D1 (2026-11-08, deviation)**: the full-corpus token count (task 4.3) was stopped after 71 minutes. The production Markdown chunker runs on one CPU core and was still on FreshStack. The FreshStack total is estimated from the 200-document slice: 1,322 tokens per document × 10,024 = about 13.2 million tokens. The BioASQ and FinanceBench totals were not counted.
- **D2 (2026-11-08, deviation)**: the machine was secure cloud, not community, because community had no RTX 4090 at any CUDA version at 00:12 UTC.
- **D3 (2026-11-08, harness bug, found in review)**: `run_part_a.py` stored `item.get("id", "")`, but the engine returns `chunk_id`. All 1,173 stored result ids are blank, so G3 compared lists of blanks and cannot fail. The repeat rows were not saved and the index went with the pod, so G3 cannot be scored from the saved data. Fixed in `ranking_lib.result_id` (refuses a blank id) and `determinism-repeat.jsonl`. G2 is not affected: it scores on `source`.
- **D4 (2026-11-08, harness bug, found in review)**: Part C compared two empty dicts, so "0 ranking changes" was never computed. Fixed in `ranking_lib.neighbour_mismatches` and recomputed from the saved vectors.
- **D5**: Part C recorded no speed for exact or fast mode (spec scenario). The token-count extrapolation covers FreshStack for the 4B model only (D1). Tasks 4.3, 5.4 and 5.5 stay open.
- **D6**: every run record says `git_dirty: true`. The cause is the untracked smoke-run copy `experiments/48-smoke/` on the pod; no tracked file differed from `cf85f671`.
- **D7**: 12 escalated pages had no OCR route (BOEING 6, Ghazali 3, Kalai 3): the pod had no OCR engine installed, so those pages kept their text layer. Code-file chunking fell back to sentence chunking 42 times on FreshStack. Both differ from the Ollama baseline path.
- **D8**: the first run recorded no `/props` snapshot or `LLAMA_ARG_*` check. The G3 rerun records both (`output/g3-rerun/server-props.jsonl`): build `b11941-19ff817fb` for both models and no `LLAMA_ARG_*` variable set.
- **D10**: FinanceBench Recall@10 (protocol section 6) was not computed. Hit@1 and Hit@page are reported. Search rows carry no collection name and answer rows keep only the text and citation count; the determinism mode ran no preflight, so the G3 repeat wrote no run record of its own (the rerun's ingest step did). Answers with claim checking cannot be confirmed as checked from the saved rows: 36 of 42 took longer than without. All are fixed in the harness for reuse; they change no gate.
- **D11**: gold-source matching was changed after the run to read the file name only (`ranking_lib.source_matches`). All stored scores came from the earlier full-path rule; rescoring all five search files under both rules gives identical numbers.
- **D9 (2026-11-08, rerun)**: G3 was rerun on a fresh RunPod RTX 4090 pod (`3b3vfm9qez83fn`, secure cloud, community had no stock) at commit `b0ff8244`, clean tree. It ran pod setup, the 11-document ingest, the 168 searches and the determinism repeat. Answers were skipped (not needed for G3). The rerun's 4B search scores equal the first run exactly (dense 15/17, MRR 0.902; dense + reranker 16/17, 0.941). Outputs: `output/g3-rerun/`.
- Known difference: OMRS has no temperature or seed setting for answers (design D2, D6a). No gate reads answer text.

### Exploratory findings

1. Embedding is a small share of wall time: on FreshStack the 4B model embedded for 21 s of 270 s. Chunking took 73 s and per-file overhead about 176 s. On FinanceBench, PDF reading takes about 360 of 393 s for every model.
2. The full-corpus token count ran the production chunker on one CPU core for 71 minutes and did not finish FreshStack (D1).

## Why it happened

1. The GGUF files, presets and pooling match the earlier Ollama setup, so retrieval stays at the same level. 4B dense misses two questions ("seating arrangement", RR 0; "primary differences between local…", RR 0.333). The reranker fixes both but pushes "literature-review prompt" out of the top 10 (RR 0), so dense + reranker scores 16/17.
2. Fast mode changes the batch order of the sums, which moves vectors by up to about 0.001 in cosine. That is enough to reorder near-tied neighbours, so it fails both Part C rules.

## Limits

1. 17 questions on 6 documents: the set is near its ceiling and catches only gross breakage.
2. Timing covers one pod class (RTX 4090, 12 vCPU) and 200-item slices.
3. Answer quality was not scored. Answers ran without a fixed seed.

## What it means for you

Experiment 35a can freeze on this runtime, in exact mode. The GPU is not what sets its run time: per-file overhead and chunking are. Before sizing the 35a pod, find out where the 0.88 s per file goes (one profiled ingest of 200 files on the Mac is enough). The FreshStack embedding itself needs only about 18 minutes for the 4B model (13.2 M tokens at 12,527 tokens/s).

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Gates, search scores, timing, Part C and the token estimate |
| `output/search.jsonl`, `output/arms-*.jsonl` | Per-question search results |
| `output/answers*.jsonl` | Answers with and without claim checking |
| `output/determinism.jsonl` | First G3 attempt (void, D3) |
| `output/g3-rerun/` | G3 rerun: search, repeat rows, mismatches (empty), `/props` snapshot, run record |
| `output/timing-*.jsonl` | Part B rows |
| `output/part-c*.json*` | Part C vectors and comparison |
| `output/run-records.jsonl` | One line per run start |
| `output/logs/` | Pod setup, smoke, sweep and Part C logs |
| `~/Development/DATA/omrs/experiments/48-pipeline-sweep-llamacpp-2026-11-01/` | Archive `exp48-output.tgz` and `copy-receipt.json` (SHA-256 `1c32d97d…`) |
