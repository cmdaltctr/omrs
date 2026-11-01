# Proposal

## Why

Parked: start only after managed-llamacpp-runtimes and dots-mocr-llamacpp-backend are merged.

PaddleOCR-VL is the fallback OCR engine. It runs its text-reading model in PaddlePaddle on the CPU, and the shipped backend (P0) needed a median 40.17 s per page in Experiment 41. Arm P4 of that experiment ran the same text-reading step on llama.cpp and needed a median 3.36 s, 12 times faster, with fewer failed pages. Once OMRS runs llama.cpp runtimes for engines (`managed-llamacpp-runtimes`), the fallback engine can use one too.

## What Changes

- **Only the text-reading step moves.** In arm P4, only PaddleOCR-VL's text-reading (VL) step ran on llama.cpp, through PaddleX `vl_rec_backend="llama-cpp-server"`. The layout step (PP-DocLayoutV3) still ran in PaddlePaddle on the CPU. So the engine keeps PaddlePaddle and gains a declared runtime. It does not become free of PaddlePaddle.
- The `paddleocr-vl` engine declares a `[tool.omrs-ocr.runtime]` block: llama.cpp build 11941, the Q8_0 model and the projector with their SHA-256, and the P4 flags `--temp 0 --image-min-tokens 144 --image-max-tokens 1280 -c 8192 -np 1`.
- The engine passes `OMRS_OCR_RUNTIME_URL` to PaddleX as the VL server URL.
- Provisioning fetches the two GGUF files and the llama.cpp `b11941` release, and checks each SHA-256.
- The fallback order does not change: dots.mocr stays primary and PaddleOCR-VL stays fallback.
- **BREAKING**: the PaddleOCR-VL fingerprint changes. Documents that the fallback engine read are re-indexed on their next ingest.

### Evidence (Experiment 41, `experiments/41-ocr-runtimes-2026-10-30/`)

| Measure | P4 (llama.cpp Q8_0) | P0 (shipped) |
| --- | --- | --- |
| Median seconds per page | 3.36 (all 257 pages) | 40.17 (221 pages it finished) |
| Pages with invented text (C5 review list) | 10 of 25 | 15 of 25 |
| Failed pages | 2 | 36 |
| Recall, pages with text only | 0.6303 | 0.6571 (difference 0.027, inside the 0.05 tolerance) |

- Gate C5 fails for both P4 and P0. Neither is free of invented text.
- The C5 review was done by an AI, not by the operator (report, Limits item 1).

### Required before ship

1. The operator's own review of the invented-text pages, for P4 and P0.
2. A real-document check through the app's OCR path.
3. The fallback order unchanged (dots.mocr primary).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ocr-worker-engines`: the PaddleOCR-VL engine declares a llama.cpp runtime for its text-reading step and keeps its layout step in PaddlePaddle.

## Impact

- **Depends on:** `managed-llamacpp-runtimes` (the host seam and `OMRS_OCR_RUNTIME_URL`) and `dots-mocr-llamacpp-backend` (the first engine on that seam). Both must be merged into `v3` first.
- **Code:** `ocr-workers/engines/paddleocr-vl/` only (manifest block, engine wiring, fetch step, pins, smoke test). No host code.
- **Spec conflict to settle at start:** `managed-llamacpp-runtimes` adds a scenario "PaddleOCR-VL unchanged" (no runtime, no URL). This change must rewrite that scenario to name an engine without a runtime block in place of PaddleOCR-VL.
- **Data:** the Q8_0 model file, the projector and a 16 MB llama.cpp binary per install.
- **Hosting (decided by the operator):** the Q8_0 file is an own `llama-quantize` output, not a file that PaddlePaddle publishes. It goes in the operator's private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted`, beside the dots.mocr files. PaddleOCR-VL is Apache-2.0, so its model card keeps the licence text and any upstream NOTICE file, and states that the file was changed (design D5).
- **Not changed:** the fallback order, the protocol version, the settings keys, the layout model.
