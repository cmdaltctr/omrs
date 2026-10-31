# Proposal

## Why

The dots.mocr OCR engine runs on PyTorch in its own worker environment. It is the only OMRS model that does not run on llama.cpp. Experiment 41 converted dots.mocr to GGUF Q8_0 and ran it on llama.cpp build 11941 over 257 pages:

- The text matched the PyTorch backend (median Dice 1.00).
- Recall and the maths checks passed.
- Peak memory fell from 22.2 GiB to 17.3 GiB.

The arm was not faster: re-timed alone, the PyTorch backend was as quick. The operator decided on 2026-10-31 to move dots.mocr to llama.cpp anyway, for three reasons: no PyTorch in the OCR workers, one runtime for every local model, and lower memory.

## What Changes

- Add a new engine folder, `ocr-workers/engines/dots-mocr-llamacpp`. Its worker runs dots.mocr through a llama.cpp server that the worker starts and stops itself. It keeps the same prompt, page rendering, token cap and Markdown conversion as the PyTorch engine.
- Provisioning fetches three pinned items into the engine folder and checks each SHA-256:
  - the converted model file (Q8_0) and its image projector (mmproj), from the operator's private Hugging Face repository;
  - the llama.cpp `b11941` release binary for the host platform.
- The PyTorch engine stays the default until the new engine passes a check on real documents through the app's own OCR path, and the operator confirms.
- After that confirmation:
  - remove the PyTorch engine;
  - give the new engine the `dots-mocr` name, so existing settings keep working;
  - write the ADR.
- **BREAKING**: the engine fingerprint changes, so the next ingest re-indexes every document in each collection. This happens once, when an operator switches.
- **BREAKING (at cut-over)**: a `dots-mocr` engine provisioned on PyTorch stops working until it is provisioned again.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ocr-worker-engines`:
  - The dots.mocr engine runs on a pinned llama.cpp server that it owns.
  - Its model files and runtime are pinned and checked by SHA-256.
  - The engine is free of PyTorch.
  - Provisioning still needs licence acceptance.
  - Parsing stays offline.

## Impact

- **New code**: `ocr-workers/engines/dots-mocr-llamacpp/`, with its engine package, fetch step, lockfile, licence notes and smoke test.
- **Removed at cut-over**: `ocr-workers/engines/dots-mocr/`, which holds PyTorch, transformers, accelerate, qwen-vl-utils and the model-code patches.
- **Host code**: none. The host resolves engines by folder name (spec: "Adding an OCR engine SHALL NOT require host code changes").
- **Tests**: new engine tests. `tests/test_ocr_worker_import_boundary.py` (which asserts that the dots-mocr lock owns PyTorch) and `tests/test_ocr_engine_dots_mocr.py` change at cut-over.
- **Docs**: `docs/guides/ingestion.md`, `docs/guides/configuration.md`, `docs/guides/architecture.md`, `ocr-workers/README.md` and the engine `LICENCE-NOTES.md`.
- **ADRs**: a new ADR supersedes the PyTorch part of ADR-072. It cites Experiment 41 and the real-document check.
- **Live app**: the hand-built workers in `~/.omrs/ocr-workers` need the new engine provisioned. The operator approves that step.
- **Data**: about 4.4 GB of model files (1.9 GB model plus 2.5 GB projector) and a 16 MB llama.cpp binary per engine install. The PyTorch model cache (5.7 GB) can go after cut-over. The copy in `~/Development/DATA/omrs` stays.
- **Not changed**:
  - PaddleOCR-VL, which stays the fallback engine.
  - The optional `torch` extra for the reranker (ADR-073).
  - The protocol version.
  - The settings keys.
