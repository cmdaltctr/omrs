# Proposal: pipeline sweep on llama.cpp

## Why

Experiment 35 becomes a `publication` experiment (`docs/proposals/first-publication-benchmark.md`, Step 2). ADR-103 says every local model in it must run through llama.cpp with a public GGUF file. The full OMRS pipeline has never run end to end that way. Every earlier end-to-end run (Experiments 2 and 3) used Ollama tags.

A failure found inside a frozen Confirmatory run costs a plan amendment or a restart. A short optimisation run on a small fixed set finds those failures first.

Experiment 35 must also choose: run locally on the measurement Mac, or rent cloud hardware. No one has timed Qwen3-Embedding 0.6B, 4B and 8B GGUF on that Mac. The proposal lists "index building on 40K abstracts takes too long on the Mac" as a risk, with "time the pipeline sweep first" as the response.

## What Changes

- Plan one new experiment, purpose `optimisation`, size Standard, category `runtime`. `omrs experiments new` gives it the next free number at apply time. No folder is created by this proposal.
- **Part A, pipeline sweep.** Run the full pipeline once, with every local language and embedding model on llama.cpp and no Ollama:
  1. Ingest PDFs and text: reader, OCR routing, normalisation.
  2. Chunk, embed with Qwen3-Embedding-4B GGUF (the planned Experiment 35 baseline), and write to LanceDB.
  3. Search in three modes: dense, hybrid, and hybrid with the reranker.
  4. Answer each question, without and with claim checking.
  5. Write one run record per run, with the runtime that the live-server check found.
- **Part B, embedding timing.** Embed a fixed slice of each benchmark corpus (200 FreshStack documents, 200 BioASQ abstracts, the 5 FinanceBench PDFs of Part A) with Qwen3-Embedding 0.6B, 4B and 8B GGUF on the measurement Mac. Record wall time, tokens and peak memory. Extrapolate to the three Experiment 35 corpora: the FinanceBench PDFs, FreshStack (10,024 documents) and BioASQ (40.2K abstracts).
- Small fixed set: Experiment 3's 6 documents and the 17 questions in Experiment 2's `ground-truth.json`, plus 5 FinanceBench PDFs with their open-sample questions.
- Exit rule: every stage runs without error; Hit@1 and MRR on the 17 questions stay close to the earlier Ollama numbers; one repeat of retrieval gives identical results.
- Serve the embedding and chat models from one llama.cpp router (`llama serve`), so the existing live-server check covers both in one call.

Out of scope: the benchmark itself (Experiment 35), Ragas, the publication rules, and any change to production defaults. The ONNX reranker and the OCR engines stay on their current runtimes, because llama.cpp cannot run them (ADR-103, Neutral).

## Capabilities

### New Capabilities

- `pipeline-sweep-evaluation`: the pre-benchmark end-to-end run on llama.cpp. Covers the fixed set, the stages that must run, the exit rule, the determinism check and the embedding timing used for the local-or-cloud decision.

### Modified Capabilities

- `experiment-validity-gates`: one added requirement. A run that uses more than one llama.cpp server checks each server against the models it serves, and the run record holds all of them.

## Impact

- Code: none in `src/` or `experiments/_lib/`. The new experiment folder holds its own scripts and their tests.
- Docs: the experiment's own `protocol.md`, `plan.json` and `report.md`.
- Experiment 35: its task 1.4 (local 0.6B, 4B and 8B GGUF timing on a slice of each corpus) reuses the Part B numbers. That change folder is not edited here.
- Dependencies: none. llama.cpp stays an external program called over HTTP (ADR-074 decision 7). `uv sync --extra llamacpp` gives the embedding client.
- Data: FinanceBench PDFs and the FreshStack slice stay in the gitignored experiment `output/` or `~/Development/DATA/omrs/`. FinanceBench is CC BY-NC 4.0 and is not committed.
