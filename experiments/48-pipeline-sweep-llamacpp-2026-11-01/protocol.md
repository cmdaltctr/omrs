# Experiment 48: Pipeline sweep on llama.cpp

- **Folder**: `48-pipeline-sweep-llamacpp-2026-11-01` (numbered 43 until 2026-11-07; see Amendments)
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: Aizat, with the a-build agent.
- **Related**: change `pipeline-sweep-llamacpp`; ADR-103 (llama.cpp GGUF runtime), ADR-074. Feeds Experiment 35 (tasks 1.4 and 1.5) and its RunPod edition 35a. Baseline references: Experiments 2 and 3.

## 1. Question

Does every OMRS pipeline stage run without error when every local model runs on llama.cpp with public GGUF files, and at what rate do the 0.6B, 4B and 8B Qwen3-Embedding models embed on the measurement Mac?

Experiment 35 freezes its plan only after this sweep passes. The Part B timing feeds its embedding-time decision.

## 2. Hypothesis

- **H1 (primary)**: every stage and every search and answer mode runs with zero errors, and retrieval on the 17-question set stays within one question of the earlier Ollama results.
- **H0 (null)**: a stage errors, or Hit@1 or MRR falls below the exit-table bounds.
- **Decision rule**: PASS when every exit-table row passes; FAIL otherwise with the failing stage named. A failure is fixed, in a separate change when it touches `src/`, before Experiment 35 freezes its plan.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| Ollama (Experiments 2 and 3) against llama.cpp GGUF through one router (OMRS-managed `llama-server` since amendment A3; was `llama serve`) | Hit@1 on 17 questions | MRR; zero stage errors; deterministic repeat | The fixed set below, build 11941, the D6a presets, seed 20261101 |

Parts: **A** the end-to-end sweep (ingest 11 documents, three search modes, answers with claim checking off and on, determinism repeat, 0.6B and 8B comparison arms). **B** embedding timing of the three models on one slice per corpus, extrapolated to the three Experiment 35 corpora. **C** fast mode against exact mode on the 4B model (lowest cosine at least 0.9999 and no top-10 ranking change, or Experiment 35 uses exact mode).

The ONNX reranker and the OCR engines stay on their current runtimes (ADR-103, Neutral). Metadata extraction runs at its default (`llamaindex`) and is timed per chunk.

## 4. Data

| Item | Value |
| --- | --- |
| Documents | The 6 Experiment 3 files (copied to `corpus/`) plus 5 FinanceBench PDFs in `output/financebench/pdfs/` |
| Questions | 17 in `ground-truth.json`; 25 FinanceBench open-sample questions in `output/financebench-questions.jsonl` |
| FinanceBench rule | Rank open-sample documents by question count, ties by name, first 5 with at most 200 pages: AMD_2022_10K (121 pages, 7 questions), BOEING_2022_10K (190, 7), AMCOR_2023_10K (156, 4), ULTABEAUTY_2023Q4_EARNINGS (9, 4), 3M_2023Q2_10Q (92, 3). 568 pages in total |
| Timing corpora | FreshStack LangChain slice (10,024 documents, seed 20260530, ID-list SHA-256 `702ea7cd…c107`); BioASQ test split (40,181 passages, revision `8a845907…`); the 5 FinanceBench PDFs |
| Gold page conversion | `evidence_page_num` is zero-indexed; `convert_evidence_page` adds one (tested) |
| Licences | FinanceBench CC BY-NC 4.0: PDFs and derived text stay in gitignored `output/`. FreshStack CC BY-SA 4.0, BioASQ CC BY 2.5 |

Every input SHA-256 sits in the `frozen` list of [plan.json](plan.json), written by script from the files themselves.

## 5. Steps

Run from this folder. The router preset file is `router.json`; the heavy-run rule applies: tell the user before each server start.

Amendment A3 (2026-11-07) replaces steps 2 and 6 to 8 where they name `llama serve` or `router.json`: the run takes place on one RunPod RTX 4090 pod, `omrs llamacpp install --flavour cuda` places build b11941 first, and OMRS's managed router starts from the scratch `omrs.jsonc` in `output/`. Change task 3.5 rewires the scripts; the commands below change only in how the router starts.

1. Prepare: `uv run --no-sync python prepare_financebench.py` (already run; freezes the 5 PDFs and the 25 questions).
2. Start the router: `llama serve --config-file router.json` (port 18080, one preset per model).
3. Part A: `uv run --no-sync python run_part_a.py --resume` (hash check, chunking guard, live-server check, run record, ingest, three search modes, answers with and without claim checking).
4. Determinism: `uv run --no-sync python run_part_a.py --mode determinism --resume` (new process, same index).
5. Comparison arms: `uv run --no-sync python run_part_a.py --mode arms --resume` (0.6B and 8B dense indexes, 17 questions, reranker off).
6. Part B: `uv run --no-sync python run_timing.py --model 0.6b|4b|8b` (one model at a time; restart the router per model).
7. Token counts: `uv run --no-sync python run_timing.py --tokenize`, then `--extrapolate`.
8. Part C: `uv run --no-sync python run_timing.py --part-c --stage exact`, then `--stage fast`, then `--stage compare` (fresh router starts).

Each step appends one line per run to `output/run-records.jsonl` and writes one JSONL file per stage in `output/`. A failed item is recorded and the run continues.

## 6. Analysis

- **Stats level**: basic. Hit@1, MRR (17 questions), Hit@page and Recall@10 (FinanceBench, reported only).
- **Gates** (the exit table, D5):

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | Every stage and every search and answer mode has zero errors | A stage broken on llama.cpp would fail inside Experiment 35's frozen run |
| G2 | Hit@1 at least 16/17 and MRR at least 0.94 for 0.6B and 8B dense (Experiment 2: 17/17, 1.000); Hit@1 at least 16/17 for 4B dense with reranker (Experiment 3: 17/17) | Catches gross breakage; the set sits at the ceiling |
| G3 | A repeated retrieval run in a new process gives identical rankings | Experiment 35 builds its statistics on a fixed index |

- FinanceBench retrieval, 4B hybrid with and without reranker, and 4B dense are reported only: no earlier number exists.
- **Stop rule**: stop a part when its input hash check or the live-server check fails. A determinism mismatch is recorded and reported, never re-rolled.
- **What each outcome means**: Pass — Experiment 35 may freeze. Fail — the failing stage is fixed first. Unclear — a stage works but a bound is missed: report both values and let Experiment 35 decide with the exit table in view.

## 7. Runtime

- **Purpose**: optimisation. **Runtime under test**: no.
- **Machine**: the measurement Mac (64 GB M5 Pro), macOS, Metal backend.
- **Local models**: all through one `llama serve` router on `127.0.0.1:18080`, llama.cpp build **11941** (read back from `GET /props` by the live check; builds before b11510 are not allowed). Full presets in the `runtime` block of [plan.json](plan.json) (design D6a: exact and fast embedding presets and the chat preset, every value written out). Part C's fast preset differs from the pinned exact preset by `parallel=8 kv-unified=true` only.

| Role | File | SHA-256 (first 12) | Build |
| --- | --- | --- | --- |
| Embedding 0.6B | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `06507c7b4268` | 11941 |
| Embedding 4B (baseline) | `Qwen3-Embedding-4B-Q8_0.gguf` | `b60ae5ce2dd6` | 11941 |
| Embedding 8B | `Qwen3-Embedding-8B-Q8_0.gguf` | `d20ddc71e8a5` | 11941 |
| Chat (answers, metadata) | `Qwen3-4B-Q8_0.gguf` | `8c2f07f26af9` | 11941 |

Files live in `DATA/omrs/benchmarks/gguf/`. The embedding tokenizer (`Qwen/Qwen3-Embedding-4B`, revision `5cf2132a`) is the token-aware chunking tokenizer; the chunking guard stops the run when the splitter resolves to `legacy_fallback`.

- **Hosted references**: none.
- **Tolerance**: Hit@1 0.059 (one question in 17) and MRR 0.06 — the largest change that still counts as the same result on a rerun.
- **Live check**: every run calls `verify_llamacpp_runtime` against the router and stores `found.as_run_record()` in its run record. Part B checks one model per plan block against its own router start.

## 8. Amendments

Each amendment is also in the `amendments` list of [plan.json](plan.json). Text above that an amendment replaces is kept and marked.

- **A1 (2026-11-01).** Metadata extraction runs disabled in every stage. Full text in `plan.json`.
- **A2 (2026-11-07).** Renumbered from 43 to 48. The merged Experiment 43 (`43-image-rescue-gate-2026-11-02`) holds 43; 48 is the next free number on `v3` at `c498a439`. No input, model, gate or metric changes. Earlier commits and the 1 November dry-run outputs still name the 43 folder.
- **A3 (2026-11-07).** Runtime and machine, from the master flow `rag-benchmark-readiness-flow` (tasks 5.2 and 5.3).
  - Router: OMRS's own managed router (`llama-server`, pinned build b11941), not the Llama app's `llama serve`, which OMRS refuses (`one-llamacpp-router` design D17). Scratch `OMRS_CONFIG_DIR` and `OMRS_STATE_DIR` inside `output/`. One `llamacpp_models` entry per model, its preset equal to the `server_args` in `plan.json`.
  - Machine: one RunPod on-demand RTX 4090 pod (Linux x86-64, the machine class of Experiment 35a), not the measurement Mac. Build: the b11941 `cuda` flavour (CUDA 12.8), placed by `omrs llamacpp install --flavour cuda`, which checks the archive SHA-256, the reported build and a CUDA device. Section 7's Mac and Metal lines describe the 1 November dry run only.
  - Consequence: Part B and Part C rates describe the RTX 4090 pod. Experiment 35a may reuse them when its pod class, GGUF files and build match. The Mac edition (Experiment 35) may not.
  - Unchanged: the four GGUF files and their SHA-256, build 11941, every preset value, the fixed set, the seed, the gates and the tolerances. The baseline embedding model stays Qwen3-Embedding-4B Q8_0.
