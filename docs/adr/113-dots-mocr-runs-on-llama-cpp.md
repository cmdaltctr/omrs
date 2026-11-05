# ADR-113: dots.mocr Runs on llama.cpp

- **Date:** 2026-11-05
- **Status:** Proposed (2026-11-05; accepted when the change merges)
- **Deciders:** Maintainer
- **Supersedes:** the PyTorch runtime part of [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md) (the PyTorch runtime in decision 3, and the model-code patches). The engine layout, the licence gate, the route order and maths routing of ADR-072 stay.
- **Related:** [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md) (OMRS runs the `llama-server`; the engine is a client), [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md) (llama.cpp GGUF for local models; MLX not allowed), [ADR-073](073-make-the-torch-extra-a-normal-choice.md) (the optional `torch` extra for the reranker, not changed), root `AGENTS.md` Gotcha 16
- **Change:** `openspec/changes/dots-mocr-llamacpp-backend/`
- **Evidence:** `experiments/41-ocr-runtimes-2026-10-30/report.md` (arm D4 and the T-control), `ocr-workers/engines/dots-mocr/SMOKE_RESULTS.md` (design D9 check)

## Context

The `dots-mocr` OCR engine ran dots.mocr on PyTorch in its own worker environment, with transformers, accelerate, qwen-vl-utils and two patches to the model code. It was the only OMRS model that did not run on llama.cpp.

Experiment 41 converted dots.mocr to GGUF Q8_0 with a bf16 image projector and ran it on llama.cpp build 11941 (arm D4) over 257 pages:

- **Quality.** The text matched the PyTorch backend (median Dice 1.00). D4 passed the KaTeX check (0 errors in 1,895 formulas), the recall floor (0.8886 against 0.8389) and the timeout check.
- **Memory.** Peak memory (client plus server) was 17.3 GiB. The PyTorch backend peaked at 22.2 GiB.
- **Speed: the gate failed.** Gate C1 asks for twice the speed of the baseline. D4 took a median of 43.97 s per page against a limit of 28.31 s (1.29 times). A re-timing of the PyTorch backend alone (the T-control, 20 pages) put the two at about the same speed (D4 0.83 times by median, 0.98 times by mean).
- **Invented text.** Gate C5 flagged 2 of 17 review pages for D4. The report rates this fail as the weaker one: the script check found no difference between D4 and the PyTorch baseline, and an AI, not the operator, did the review.

By its gates, Experiment 41 gave no runtime decision.

## Decision

1. **dots.mocr runs on llama.cpp.** The operator decided on 2026-10-31 to move anyway, for three reasons that the gates do not measure:
   - no PyTorch in any OCR engine environment;
   - one runtime for every local model;
   - lower peak memory (17.3 GiB against 22.2 GiB).

   Speed is not a reason. The T-control shows no gain.
2. **The engine keeps the name `dots-mocr`.** The PyTorch engine is removed. The llama.cpp engine moves to `ocr-workers/engines/dots-mocr`, with package `omrs_ocr_dots_mocr` and entry point `dots-mocr`, so saved settings keep working. The `backend_id` stays `dots_mocr_llamacpp`, because it names the backend.
3. **The engine declares its runtime; OMRS runs it** (ADR-109). The engine's `pyproject.toml` holds `[tool.omrs-ocr.runtime]`: the pinned `llama-server`, build 11941, the flags of arm D4 and both model files with their SHA-256. The host checks the build and the hashes before a start and gives the worker the address in `OMRS_OCR_RUNTIME_URL`. The worker starts no process.
4. **Everything is pinned and hashed.** Provisioning downloads the model `dots-mocr-Q8_0.gguf` and the projector `dots-mocr-mmproj-bf16.gguf` from the private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted` at a pinned commit, and the llama.cpp release `b11941` for the host platform. It checks every SHA-256. The values live in `pins.py`, and a test pins the runtime block to them.
5. **The prompt, the page render, the token cap and the Markdown conversion stay** as the PyTorch backend had them. A test pins the prompt by its SHA-256.
6. **Each request names the model `dots-mocr`.** `llama-server` with one model ignores the name. Ollama and mlx-vlm refuse a request without one.
7. **llama.cpp is the only parity-checked runtime.** Ollama and MLX can run the engine, but neither gave llama.cpp's text on a 10-page check (below). Each needs its own parity run, and an index built on either needs its own fingerprint value.

## Real-document check (design D9)

The check ran through the app's OCR path (`build_ocr_routes`), not the experiment client, on one Apple silicon Mac with llama.cpp build 11941 (Metal). The operator confirmed cut-over on 2026-11-05 (master flow gate G10).

| Rule | Result |
| --- | --- |
| Parity: every page Dice 0.99 or more against arm D4 | Pass. Lowest Dice 1.0 on all 22 pages. |
| Parity: at least 18 of 22 pages identical to D4 | Pass. 22 of 22 identical. |
| Parity: median Dice against the PyTorch text 0.99 or more | Pass. Median 1.0. |
| Offline smoke on `eq01` p2 and p3, network blocked | Pass. Both pages gave Markdown. |
| Ingest `eq01`, `io06`, `rf06`; search finds a phrase from an OCR page of each | Pass (page mode, 2026-11-03). `rf06` p29 "Sevilla 17 de Agosto" is found. |
| KaTeX 0.16.22 renders every `eq01` formula | Pass. 300 formulas, 0 errors. |
| Integrations page shows the engine ready at 1,280 px and 390 px | Pass. |
| No `llama-server` left after the CLI and the web app stop | Pass. `stopped_by: last-client`. |

Seconds per page over the 22 parity pages: minimum 9.2, median 34.6, maximum 47.8.

**Other runtimes (2026-11-02, 10 pages from 8 documents, not a pass rule):**

| Runtime | Pages identical to llama.cpp | Lowest Dice |
| --- | --- | ---: |
| llama.cpp b11941 | 22 of 22 (parity check) | 1.000 |
| Ollama 0.40.13, the same two pinned files | 7 of 10 | 0.767 |
| mlx-vlm 0.7.11, `mlx-community/dots.mocr-8bit` | 3 of 10 | 0.901 |

Ollama changed words on three pages (handwritten Spanish and Arabic). MLX changed words on Bengali, Arabic and handwritten pages, and dropped formatting in formulas. MLX ran as a comparison only (ADR-103).

## Consequences

### Positive

- No OCR engine environment holds PyTorch. A test asserts that no engine lock holds `torch`, `torchvision`, `transformers` or `accelerate`.
- Every local model runs on llama.cpp, through one runtime manager.
- Peak memory falls from 22.2 GiB to 17.3 GiB, and the host stops the server after 10 minutes with no request.
- The model files and the runtime binary are reproducible: pinned, hashed and checked before each start.

### Negative

- **One re-index.** The engine fingerprint changes (backend `dots_mocr_llamacpp`, pipeline `prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1`). The next ingest re-indexes each document once.
- **Re-provision needed.** A `dots-mocr` engine provisioned on PyTorch stops working until it is provisioned again.
- **A token at provisioning.** The repository is private (licence clause 4.4), so provisioning needs `hf auth login` or `HF_TOKEN`. A parse needs neither.
- **No speed gain.** Experiment 41 shows none.
- **Linux is untested.** The pinned Ubuntu x64 archive is a CPU build, and no CUDA build is pinned. Run `parity_check.py` on a new machine first.
- **A new llama.cpp build needs a new change:** a new pin, a new pipeline revision and a re-index.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **Keep the PyTorch engine** | It keeps PyTorch in an engine environment and a second runtime, and it uses more memory. The quality is the same. |
| **Keep the name `dots-mocr-llamacpp` for good** | It breaks every saved `ocr_engine_primary = "dots-mocr"` and changes the docs for no benefit. |
| **A backend switch inside one engine folder** | PyTorch stays in that lockfile, and one environment carries two runtimes. |
| **The worker starts its own server** | Two OMRS processes started two workers that shared a cache folder, and one stopped the other's server (ADR-109). |
| **The system or Llama app `llama-server`** | Homebrew updates it without warning, which changes the output. The Llama app router keeps one model loaded and would unload Chat. |
| **Ollama or MLX as the runtime** | Neither gave llama.cpp's text on the 10-page check. MLX is not an allowed runtime (ADR-103). |
| **Convert the model at provisioning** | The llama.cpp converter needs PyTorch. |

## References

- `openspec/changes/dots-mocr-llamacpp-backend/` (proposal, design D1 to D9, tasks)
- `experiments/41-ocr-runtimes-2026-10-30/report.md`
- `ocr-workers/engines/dots-mocr/SMOKE_RESULTS.md` and `smoke_evidence/`
- `ocr-workers/engines/dots-mocr/LICENCE-NOTES.md`
- [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md), [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md), [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md)
