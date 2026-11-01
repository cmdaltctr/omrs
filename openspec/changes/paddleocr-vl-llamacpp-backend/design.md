# Design

## Context

See proposal.md, "Why" and "Evidence". The current state:

- `ocr-workers/engines/paddleocr-vl/src/omrs_ocr_paddleocr_vl/engine.py` builds one `PaddleOCRVL(device="cpu", ...)` pipeline and keeps it for the life of the worker. It declares no runtime.
- Experiment 41 arm P4 (`run_ocr.py`, class `PaddleClient`) kept the P0 settings and changed only the VL step: `PaddleOCRVL(pipeline_version="v1.6", device="cpu", use_ocr_for_image_block=True, format_block_content=True, vl_rec_backend="llama-cpp-server", vl_rec_server_url=<base url>/v1, vl_rec_api_model_name=<model>)`, with `temperature=0` and the P0 token cap on `predict`.
- The layout model PP-DocLayoutV3 stays in PaddlePaddle (plan.json, `paddleocr_vl_wiring`).
- `managed-llamacpp-runtimes` gives the seam: the `[tool.omrs-ocr.runtime]` block, the host's build and hash checks, the request lock for `-np 1` runtimes, and `OMRS_OCR_RUNTIME_URL`.

## Goals / Non-Goals

**Goals:**

- Run PaddleOCR-VL's VL step on the pinned llama.cpp runtime with the P4 settings.
- Keep the layout step, the Markdown output and the fallback order as they are.

**Non-Goals:**

- Removing PaddlePaddle from the engine.
- Fixing invented text on Bengali, Arabic or other pages. That is a separate experiment (Experiment 41 report, next step).
- Changing the primary engine.

## Decisions

### D1. Declared runtime with the P4 pins

| Item | Value |
| --- | --- |
| Source repository | `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` at `511b09642bb324401f15f97cc23bc67e8f0a291d` |
| Model | `PaddleOCR-VL-1.6-Q8_0.gguf`, own `llama-quantize` Q8_0, SHA-256 `2bda93a416339f2d9f06accae505600544a9e72cc159d0cd1af4c0f679866e1c` |
| Projector | `PaddleOCR-VL-1.6-GGUF-mmproj.gguf`, SHA-256 `204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a` |
| Build | 11941 |
| Flags | `--temp 0 --image-min-tokens 144 --image-max-tokens 1280 -c 8192 -np 1` |

- The model is the `-m` file entry and the projector is the `--mmproj` file entry. The host adds the host and the port.
- The llama.cpp binary comes from the same `b11941` release and archive hashes that `dots-mocr-llamacpp-backend` pinned. Each engine keeps its own copy in its own cache, because the host checks paths inside each engine's cache only.

### D2. The engine passes the URL to PaddleX

- The engine reads `OMRS_OCR_RUNTIME_URL` and builds the pipeline with `vl_rec_backend="llama-cpp-server"` and `vl_rec_server_url=<url>/v1`, as P4 did.
- Missing or non-loopback URL: a parse error that names the variable.
- When the URL changes, the host restarts the worker (`managed-llamacpp-runtimes` D10), so the pipeline singleton never holds an old URL.
- PaddleX may send several block requests for one page at once. With `-np 1`, llama-server queues them inside one parse. The host's request lock covers the whole parse, so another process waits outside, and the parse timeout covers only this parse (`managed-llamacpp-runtimes` D6).

### D3. Fingerprint

- `backend_id` stays `paddleocr_vl`, so diagnostics keep naming the engine.
- The pipeline revision gains `llamacpp-b11941+q8_0`, and the model identity names the GGUF pins. The fingerprint changes, so fallback-read documents re-index once.

### D4. Ship checks

- The operator reviews the invented-text pages of P4 and P0 (the 25-page C5 list) and decides.
- A real-document check runs through the app's OCR path with dots.mocr made unavailable, so the fallback serves. Rules are set by the operator before the run.

### D5. Hosting and licence (operator decision)

- The Q8_0 file goes in the operator's private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted`, beside the dots.mocr files.
- The model card of that repository SHALL keep the Apache-2.0 licence text, keep any upstream NOTICE file, and state that the file was changed: re-quantised to Q8_0 with `llama-quantize`, llama.cpp build 11941, from `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` at `511b09642bb324401f15f97cc23bc67e8f0a291d`.
- The projector stays as published by PaddlePaddle. Its source is the same pinned commit.
- The repository is private, so the fetch step reads a Hugging Face token from the environment. A missing token gives a fetch error that names the variable. The token is never written to a file or a log. If the repository is made public later, the same model card applies.

## Risks / Trade-offs

- [Invented text on some scripts] → C5 fails for P0 too, so P4 is not worse on the list. The operator review is a ship condition.
- [Model hosting and licence] → decided (D5). The file goes in a private repository with a model card that carries the Apache-2.0 terms. Provisioning cannot ship until the file is uploaded and its commit is pinned.
- [Two OCR runtimes in memory] → the fallback runtime starts only when the fallback route serves, and stops after 10 minutes idle.

## Open Questions

- Which value P4 passed as `vl_rec_api_model_name`. Task 1.1 reads it from the Experiment 41 run log.
