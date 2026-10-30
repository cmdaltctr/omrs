# Experiment 41: OCR Runtimes, GGUF against MLX

## Why

Experiment 37 accepted dots.mocr as the primary OCR engine and left two costs open. PaddleOCR-VL on CPU timed out on 34 of 257 pages (finding F4). dots.mocr peaked at 22.2 GiB on PyTorch MPS (finding F5).

ADR-103 makes llama.cpp GGUF the runtime for local models in experiments. The first plan (`experiment-41-mlx-ocr-backends`, 2026-10-06) compared MLX only. On 2026-10-30 the operator decided that MLX arms are comparison arms only. A runtime decision needs a llama.cpp arm.

OMRS needs a measured answer on the same 257 pages: can a llama.cpp GGUF arm, or an MLX arm, replace the shipped backend of each engine without losing output quality?

## What Changes

- Add Experiment 41 under `experiments/41-ocr-runtimes-2026-10-30/` with a protocol, a plan and, after operator approval, runs.
- Compare five arms per engine on the Experiment 37 page lists (E-maths 40, E-scan 28, E-script 189):
  - dots.mocr: PyTorch MPS (shipped, reused); MLX bf16 and 8-bit (comparison); llama.cpp GGUF bf16 and Q8_0 from our own conversion (decides).
  - PaddleOCR-VL: CPU (shipped, reused); MLX bf16 and 8-bit from our own conversion (comparison); llama.cpp GGUF 16-bit from the official repository and Q8_0 from our own conversion (decides).
- Gates C1 to C5 decide. C6 and C7 inform. The operator set these gates on 2026-10-06.
- Only a llama.cpp arm that passes can lead to a follow-up OpenSpec change for an engine.
- Hold four approvals in `plan.json`, all `false`: install, downloads, licence check and OCR run budget.
- Extend the licence check (DR-2) to our own GGUF conversion of dots.mocr and to the MLX 8-bit conversion.
- Change no engine folder, route, default or dependency.

## Capabilities

### New Capabilities

- `ocr-runtime-evaluation`: defines the evaluation contract for comparing the llama.cpp GGUF and MLX runtimes of an OCR engine with the engine's shipped backend.

### Modified Capabilities

- None.

## Impact

- Adds experiment artefacts only. Gitignored environments and weights stay inside the experiment folder or the model cache.
- No change to `ocr-workers/`, OMRS source, settings or the base install.
- A passing llama.cpp arm leads to a separate OpenSpec change for that engine. A failing one leaves the engine on its shipped backend.
- Installs, downloads, the licence check and the run need the operator's approval first.
