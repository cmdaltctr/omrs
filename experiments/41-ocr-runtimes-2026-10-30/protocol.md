# Experiment 41: OCR runtimes, GGUF against MLX

- **ID**: `41-ocr-runtimes-2026-10-30`
- **Date planned**: 2026-10-30
- **Record**: [`experiment.json`](experiment.json) holds the status.
- **Replaces the plan**: `41-mlx-ocr-backends-2026-10-06`, which exists only on branch `feat/experiment-41-mlx-ocr-backends`. Its page lists, gates and open decisions carry forward. Its scope does not.
- **Relation**: OpenSpec change `experiment-41-ocr-runtimes`; Experiment 37 findings F4 and F5; ADR-074 and ADR-103 (llama.cpp GGUF for local models)
- **Plan**: [`plan.json`](plan.json) (arms, page lists, gates, approvals, open decisions and items)
- **Number**: 41. Number 40 is reserved in NiftyPM for AIE-101.

## Question

Which runtime can serve each OCR engine without losing output quality?

The two engines are dots.mocr and PaddleOCR-VL. Each engine has a shipped backend. Experiment 37 measured both backends.

The first choice is llama.cpp, because ADR-103 names llama.cpp GGUF as the runtime for local models in experiments. MLX is a second option. MLX runs only on Apple silicon, and ADR-103 withdrew the MLX 8-bit fallback for decision models. MLX arms in this experiment are comparison arms. They show what MLX does. They cannot choose a runtime.

## Why this experiment exists

Experiment 37 accepted dots.mocr as the primary OCR engine and left two costs open.

1. PaddleOCR-VL on CPU timed out on 34 of 257 pages (finding F4).
2. dots.mocr peaked at 22.2 GiB of memory on PyTorch MPS (finding F5).

A two-page MLX test on 2026-10-05 ran PaddleOCR-VL in 6.6 s and 9.4 s per page, against 87 s and 133 s on CPU. That test was a scratch session. Its environment is gone, and it covered two pages of one paper. It supports no decision.

The operator decided on 2026-10-30 (option 1) that a runtime decision needs a llama.cpp arm. This plan follows that decision.

## Hypothesis, null and decision rule

**H1 (primary).** At least one of the two scored llama.cpp GGUF arms (D4 for dots.mocr, P4 for PaddleOCR-VL) meets gates C1 to C5 against its engine's shipped backend.

**Null.** Neither D4 nor P4 meets all of C1 to C5 against the shipped backend of its engine.

**Decision rule.**

Each engine has one scored GGUF arm: D4 for dots.mocr, P4 for PaddleOCR-VL. Only these two arms decide.

1. If D4 passes, open a follow-up OpenSpec change for a llama.cpp path for dots.mocr.
2. If P4 passes, open a follow-up OpenSpec change for a llama.cpp path for PaddleOCR-VL.
3. If the GGUF arm of an engine fails, that engine keeps its shipped backend.
4. An MLX arm never leads to an engine decision.
5. If an MLX arm passes and the GGUF arm of its engine fails, the report says so and stops.

## Arms

Each engine has one shipped arm and two scored 8-bit arms (DR-4, 2026-10-30): one MLX and one GGUF. Each new arm is compared with its engine's shipped arm. Two 16-bit arms per engine are diagnostics. They run only when an 8-bit arm fails a quality gate (see "Conditional 16-bit diagnostic").

The vision encoder (mmproj file) stays 16-bit in every GGUF arm. Only the language model is quantised. The MLX 8-bit builds quantise as their publishers chose. The report records the difference.

### dots.mocr

| Arm | Backend | Weights | Role | Source |
| --- | --- | --- | --- | --- |
| D0 | PyTorch MPS, bf16 | `rednote-hilab/dots.mocr` at `e539fbb5` | baseline (shipped) | reuse Experiment 37 output |
| D2 | MLX, 8-bit | `mlx-community/dots.mocr-8bit` at `6d9e750b` | comparison, no decision | new run |
| D4 | llama.cpp GGUF, Q8_0 | own conversion of `rednote-hilab/dots.mocr` at `e539fbb5` to bf16, then `llama-quantize` to Q8_0; own bf16 mmproj; cross-check `lodrick-the-lafted/dots.mocr-gguf` Q8_0 | runtime, decides | new run |
| D1 | MLX, bf16 | `mlx-community/dots.mocr-bf16` at `90fe26b4` | diagnostic for D2 only | conditional |
| D3 | llama.cpp GGUF, bf16 | the bf16 intermediate of the D4 conversion | diagnostic for D4 only | conditional |

### PaddleOCR-VL

| Arm | Backend | Weights | Role | Source |
| --- | --- | --- | --- | --- |
| P0 | CPU | `PaddlePaddle/PaddleOCR-VL-1.6` (shipped) | baseline (shipped) | reuse Experiment 37 output |
| P2 | MLX, 8-bit | `OpenGryd/PaddleOCR-VL-1.6-MLX-8bit` at `dba7c66b` | comparison, no decision | new run |
| P4 | llama.cpp GGUF, Q8_0 | `llama-quantize` to Q8_0 of the official `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` file at `511b0964`; official 16-bit mmproj | runtime, decides | new run |
| P1 | MLX, 16-bit | `OpenGryd/PaddleOCR-VL-1.6-MLX-16bit` at `966b8ea5` | diagnostic for P2 only | conditional |
| P3 | llama.cpp GGUF, 16-bit | the official file at `511b0964`, unquantised | diagnostic for P4 only | conditional |

### Comparisons

- **Gated.** Each 8-bit arm against its engine's shipped arm: D2 and D4 against D0; P2 and P4 against P0.
- **Matched runtime (reported).** GGUF Q8_0 against MLX 8-bit: D4 against D2, P4 against P2. The pair is not precision-matched. Q8_0 quantises linear tensors in blocks of 32 elements with a symmetric scale, and the mmproj stays 16-bit. MLX 8-bit uses affine quantisation with group size 64 (`config.json` of `mlx-community/dots.mocr-8bit` at `6d9e750b`: bits 8, group_size 64, mode affine; read through the Hugging Face API on 2026-10-30). In that build the vision tower is not quantised: `model.safetensors.index.json` lists no `.scales` entry for its 304 vision tensors. The OpenGryd 8-bit build of PaddleOCR-VL uses the same settings and has 84 scale tensors among its 503 vision-named tensors, so part of its vision stack is quantised. The two pairs also differ in the image format: PaddleX sends PNG blocks to `llama-cpp-server` and JPEG blocks to `mlx-vlm-server` (`predictor.py`, line 595), so P2 receives JPEG blocks and P4 receives PNG. The comparison is reported only.
- **Diagnostic (reported, only when triggered).** 16-bit against 8-bit on the same runtime: D1 against D2, D3 against D4, P1 against P2, P3 against P4.

### Conditional 16-bit diagnostic

An 8-bit arm differs from its baseline in two ways: the runtime and the weight precision. A quality failure alone cannot say which one caused it. The diagnostic separates the two.

1. **Trigger.** An 8-bit arm fails C3, C4 or C5. C1 and C2 (speed and timeouts) do not trigger it.
2. **Arm.** The 16-bit arm of the same runtime and engine (table above).
3. **Pages.** The pages of the failed gate only:
   - C3: the 68 pages of `E-maths` and `E-scan`.
   - C4: 40 `E-script` pages, sampled with seed 41.
   - C5: the pages of the failed arm's review list.
4. **Pass rule.** The threshold is the failed gate's own tolerance, applied to the baseline arm's value on the same pages:
   - C3: the baseline KaTeX error rate on the 68 pages plus 0.01 (absolute).
   - C4: the baseline median recall on the same 40 seeded pages minus 0.05.
   - C5: the operator reviews the diagnostic output on the same review pages and finds no invented text.
5. **Reading.** The 16-bit arm passes this rule: the 8-bit quantisation caused the failure. It fails: the runtime caused it. The attribution is approximate. Every GGUF arm keeps a 16-bit mmproj, and MLX 8-bit quantises different tensors. The diagnostic cannot isolate one factor.
6. **Limits.** The diagnostic is descriptive only. It never changes the verdict of the 8-bit arm. It cannot make that arm pass. A 16-bit pass supports, at most, a separate follow-up experiment on the 16-bit arm with all 257 pages.
7. **Cost.** Nothing when no 8-bit arm fails. Otherwise one more download (D1 6.1 GB, P1 1.8 GB) or none (D3 and P3 already exist locally), and about 20 to 60 minutes per triggered arm.

## Facts checked on 2026-10-30

These facts come from read-only Hugging Face API checks on 2026-10-30. Nothing was downloaded or run. A first version of this plan (commit `16656b7`) said that dots.mocr had no GGUF and that PaddleOCR-VL 1.6 had no MLX weights. Both claims were wrong. This section replaces them.

1. **`dots-studio/dots.mocr` and `rednote-hilab/dots.mocr` hold the same weights.** Both report commit `e539fbb5`, the pinned revision. Both shards have the same SHA-256 (`d8f4bc75…`, `0101b36f…`). A conversion tagged with either base comes from the shipped weights.
2. **dots.mocr GGUF builds exist. All are community builds.** No GGUF comes from rednote-hilab or ggml-org.

   | Repository | Revision | Files used or relevant |
   | --- | --- | --- |
   | `lodrick-the-lafted/dots.mocr-gguf` | `180dcd99` | bf16 3.56 GB, Q8_0 1.89 GB, mmproj bf16 2.53 GB, mmproj Q8_0 1.34 GB |
   | `prithivMLmods/dots.mocr-GGUF` | not pinned | BF16, F16, Q8_0, mmproj bf16, f16, Q8_0 |
   | `richardyoung/dots.mocr-GGUF` | not pinned | Q8_0, mmproj F16 |
   | `anujkosambi/dots.mocr-Q8_0-GGUF` | not pinned | Q8_0, mmproj Q8_0 (made with gguf-my-repo) |

   The gguf-my-repo builds use the llama.cpp converter, and every repository ships an mmproj file. So the llama.cpp converter accepts dots.mocr (llama.cpp PR 17575 added dots OCR). Load and output quality at build 11941 still need a check (OI-2).
3. **D4 (and its D3 diagnostic) use our own conversion (operator choice, 2026-10-30).** The conversion ties the arm to the pinned revision and the pinned llama.cpp build. The `lodrick-the-lafted` Q8_0 file is a cross-check only. Its output on the smoke pages must match D4 (OI-9).
4. **dots.mocr MLX builds.** `mlx-community/dots.mocr-bf16` (`90fe26b4`, 6.08 GB) and `mlx-community/dots.mocr-8bit` (`6d9e750b`, 4.41 GB). Both cards say MIT and name mlx-vlm. The 8-bit card names `dots-studio/dots.mocr` as its base. Fact 1 shows that this is the same model.
5. **PaddleOCR-VL 1.6 GGUF.** The official `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` (`511b0964`, Apache-2.0) holds `PaddleOCR-VL-1.6-GGUF.gguf` (0.94 GB, no quant label, probably 16-bit for a 0.9B model; OI-3) and `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (0.88 GB). Community Q8_0 files exist (`mradermacher`, `cstr`, `SanjeevSOLANKI`, `nopesadly`). P4 quantises the official file with `llama-quantize` instead, so that P3 and P4 share one source.
6. **PaddleOCR-VL 1.6 MLX builds.** `OpenGryd/PaddleOCR-VL-1.6-MLX-16bit` (`966b8ea5`, 1.81 GB) and `OpenGryd/PaddleOCR-VL-1.6-MLX-8bit` (`dba7c66b`, 1.09 GB). Both are Apache-2.0, name `PaddlePaddle/PaddleOCR-VL-1.6` as their base and name mlx-vlm. Other 1.6 MLX builds: `mlx-community` 4-bit and 5-bit (out of scope), `translate-studio` 6-bit and 8-bit, `jmbarrancoidener` 8-bit. The `mlx-community/PaddleOCR-VL-*` builds without "1.6" use an older ERNIE-4.5-0.3B base and are out of scope.

## Corpus and ground truth

No new documents. Reuse everything from Experiment 37, without relabelling.

| Run | Pages | Ground truth |
| --- | ---: | --- |
| `E-maths` | 40 | maths labels (sha256 `324ef438`, frozen); KaTeX check only |
| `E-scan` | 28 | operator noise review |
| `E-script` | 189 | Experiment 33 reference transcriptions (split body text) |
| **Total** | **257** | |

The page lists are frozen in `plan.json` (`page_lists`, SHA-256 `09f13055`). They match Experiment 37.

The Experiment 37 outputs and corpus are gitignored. They sit in the `omrs-v3` worktree, at `../omrs-v3/experiments/37-dots-mocr-routing-acceptance-2026-09-30/`. This experiment reads them there. It does not copy them without a hash check.

## Runtime pinning

The GGUF arms run through llama.cpp build 11941 (commit `19ff817fb`), as ADR-103 requires.

- The `runtime` block of `plan.json` is added before the first score. It holds the real SHA-256 of each weights file. The checker refuses the all-zero placeholder, so this plan does not put a placeholder hash in that block.
- Before the first score, `verify_llamacpp_runtime` (`experiments/_lib/llamacpp_runtime.py`) checks the build and each file hash. A wrong build or hash stops the run.
- Each run writes a run record through `experiments/_lib/run_record.py`.
- The server runs on loopback only.
- `runtime_under_test` is `true` for the GGUF arms. Each GGUF arm records its build and the SHA-256 of each weights file.
- The server flags that change output are pinned in the `runtime` block before the plan freeze: `-c`, `--image-min-tokens`, `--image-max-tokens`, `--temp 0` and `--mmproj` (see "Preprocessing parity"). A setting changed after the freeze is a dated amendment.

### PaddleOCR-VL wiring

- **P4** uses PaddleOCR `PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="llama-cpp-server", vl_rec_server_url=<loopback llama-server>)`, per the official `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` README at `511b0964`.
- **P2** uses `PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="mlx-vlm-server", vl_rec_server_url=<loopback mlx-vlm server>)`.
- `pipeline_version` is pinned to `v1.6` on every P arm.
- P0 passes no `pipeline_version` (`ocr-workers/engines/paddleocr-vl/src/omrs_ocr_paddleocr_vl/engine.py`, line 90: `PaddleOCRVL(device="cpu", use_ocr_for_image_block=True, format_block_content=True)`). The PaddleOCR default is `v1.6` (`paddleocr/_pipelines/paddleocr_vl.py`, line 26). The Experiment 37 summary records paddleocr 3.7.0 and paddlex 3.7.2, the same versions as the engine lock. The `model = ("PaddleOCR-VL", "1.6")` fingerprint (`engine.py`, line 247) is a fixed string and is not evidence of the pipeline version. P0's effective version is `v1.6` by the default alone (OI-11 closed).
- The layout model is PP-DocLayoutV3, the model shipped with the v1.6 pipeline (`paddlex/configs/pipelines/PaddleOCR-VL-1.6.yaml`). It is the same model in every P arm. Only the VL recognition step changes.

The MLX arms run through `mlx-vlm`. They are not in the `runtime` block, because the block allows llama.cpp only, unless `runtime_under_test` is set.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | Runtime | shipped backend (baseline); MLX 8-bit; llama.cpp GGUF Q8_0. 16-bit only in the conditional diagnostic |
| Dependent | Speed | seconds per page, median and 90th percentile |
| Dependent | Memory | peak physical footprint, client and server summed |
| Dependent | Reliability | timeouts, empty results, conversion or load failures, restarts |
| Dependent | Formula validity | KaTeX 0.16.22 render error rate |
| Dependent | Script recall | token recall on `E-script`, Experiment 33 tokeniser |
| Dependent | Invented text | operator verdict on the review list |
| Dependent | Similarity | token Dice coefficient against the baseline arm, per page |
| Controlled | Pages | the same 257 pages as Experiment 37 |
| Controlled | Prompt, render size, token cap, decoding | the dots.mocr engine constants (`prompt_layout_all_en`, 200 DPI with the engine's long-side rule, 8192 tokens, greedy); the PaddleOCR-VL engine settings (4096 tokens per block request). See "Preprocessing parity" and "Token cap rule" |
| Controlled | Post-processing | the dots.mocr `layout.py` (header and footer dropped, one `$$` pair per display formula) on every dots.mocr arm |
| Controlled | Request timeout | 300 s per page |
| Controlled | Machine load | one arm at a time, with no other GPU job |

### Preprocessing parity

The runtime must be the only variable. Each runtime resizes the page image in its own way. The image token flags come from the processor configs and are pinned before the plan freeze. The parity check on the smoke pages (procedure step 8) confirms them.

**Baseline, dots.mocr (D0).**

- Render: pypdfium2 at 200 DPI. The scale rises so the long side is at least 1600 px: `scale = max(200/72, 1600/max(page size in points))`. Source: `ocr-workers/engines/dots-mocr/src/omrs_ocr_dots_mocr/engine.py`, lines 40-41 (`RENDER_DPI`, `MIN_LONG_SIDE_PX`) and line 126.
- Resize: `qwen_vl_utils.process_vision_info` (line 143), then the HF processor (line 144). The engine passes no `min_pixels` or `max_pixels` to `process_vision_info`. The `qwen_vl_utils` limits are 4 and 16384 image tokens (`vision_process.py`, lines 26-27, in the engine environment).
- Processor limits: `preprocessor_config.json` in the model folder sets `min_pixels` 3136, `max_pixels` 11,289,600, `patch_size` 14 and `merge_size` 2. One image token covers 28 x 28 = 784 px. In tokens, the minimum is 4 (3136 px) and the maximum is 14,400 (11,289,600 px).
- Baseline grid: pass the rendered image through the HF processor and read `image_grid_thw`. The token count is the grid product divided by 4. No model run is needed.

**Baseline, PaddleOCR-VL (P0).** The P0 pipeline resizes each layout block crop to the limits `min_pixels` 112,896 and `max_pixels` 1,003,520 (`paddlex/inference/pipelines/paddleocr_vl/pipeline.py`, lines 663-666, paddlex 3.7.2). In tokens of 784 px, the minimum is 144 and the maximum is 1280. For `llama-cpp-server` and `mlx-vlm-server`, PaddleX does not apply these limits. It only warns that the backend "does not support `max_pixels`" (`paddlex/inference/models/doc_vlm/predictor.py`, lines 536-560) and sends the raw crop. The backend must therefore match the P0 limits itself.

**D arms.**

| Arm | Setting |
| --- | --- |
| D4 (llama.cpp) | `--image-min-tokens 4 --image-max-tokens 14400` |
| D2 (MLX) | processor limits `min_pixels` 3136 and `max_pixels` 11,289,600, from the model's `preprocessor_config.json`; confirm at the parity check that `mlx-vlm` applies them |

**P arms.**

| Arm | Setting |
| --- | --- |
| P4 (llama.cpp) | `--image-min-tokens 144 --image-max-tokens 1280` (the official mmproj default is 1,003,520 pixels, the same upper limit; README of `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` at `511b0964`) |
| P2 (MLX) | processor limits `min_pixels` 112,896 and `max_pixels` 1,003,520 |

For the dots.mocr mmproj of our own conversion, read the default `clip.vision.image_max_pixels` from the file metadata and record it. The flags above set the limits, so no mmproj file needs an edit. If a file must change anyway, save the changed file as a pinned file with its own SHA-256 in the `runtime` block. Never edit a pinned file in place.

**Rule.** The parity check runs on the smoke pages (`eq01` p2 and p3) for each 8-bit arm, in procedure step 8, before the plan freeze. It checks token grids only and scores nothing.

- D arms: compare the resized grid with `image_grid_thw` of the baseline. At most one patch row or one patch column of difference is allowed.
- P arms: apply the same test per layout block. The baseline grid for a block comes from the P0 resize rule on the same crop. No model run is needed.
- If a grid differs by more, stop that arm and fix the setting before the freeze.
- If build 11941 ignores `--image-min-tokens` or `--image-max-tokens`, stop that arm and record a finding (OI-10). Do not loosen the tolerance.
  - Note 2026-10-31: build 11941 does ignore both flags for these projectors (OI-10). Before the freeze, the operator decided on 2026-10-30 to continue D4 and P4, with the limits pinned through the mmproj SHA-256 (DR-5 in `plan.json`). DR-5 supersedes this stop rule for D4 and P4. The rule text above is kept as written.

**Pinned llama-server flags.**

| Flag | D4 | P4 |
| --- | --- | --- |
| `--image-min-tokens` | 4 | 144 |
| `--image-max-tokens` | 14400 | 1280 |
| `-c` | 14,400 + prompt tokens + 8192 | 1280 + prompt tokens + 4096 |
| `--temp` | `0` | `0` |
| `--mmproj` | the mmproj file of the arm | the mmproj file of the arm |

The `-c` values go in the `runtime` block.

**Pinned client settings.** `temperature` 0. For D arms, `run_ocr.py` sets `temperature` 0 and `max_tokens` 8192 on the chat request. For P arms, `PaddleOCRVL.predict()` accepts `temperature` and `max_new_tokens` (`paddlex` `pipeline.py`, lines 784-788). Pass `temperature` 0 and `max_new_tokens` 4096, the P0 value (see "Token cap rule").

### Token cap rule

**D arms.** A page hits the cap when `completion_tokens >= 8192`. That page yields an empty result. MLX uses its generated token count for the same test.

- Baseline rule for dots.mocr: `engine.py` line 111 passes `hit_token_cap=new_tokens >= MAX_NEW_TOKENS` (`MAX_NEW_TOKENS = 8192`, line 42). `layout.py`, lines 114-115, returns `""` with reason `token_cap`.

**P arms.** The P0 cap is 4096 tokens per block request, not 8192.

- The engine calls `pipeline.predict(input=...)` with no `max_new_tokens` (`paddleocr-vl/.../engine.py`, line 132).
- PaddleX then passes `"max_new_tokens": None` in `vlm_kwargs` (`pipeline.py`, lines 966-972), and lines 504-505 set it to 4096. The 8192 default (`predictor.py`, lines 229-232 and 513-516) is never reached. The pipeline YAML has no override.
- P arms pass `max_new_tokens=4096`.
- P0's reused output keeps truncated block text. A P arm keeps truncated text in the same way. It logs each block with `completion_tokens >= 4096` as a cap hit. The log is information only. A cap hit does not empty the page.

Not changed: engine folders, routes, settings defaults, the maths detector, and the pinned PyTorch dots.mocr revision `e539fbb52280393adc081b289ec597430a0f9031`.

## Gates

The operator set these gates on 2026-10-06. They apply to every new arm against its own baseline. The operator did not change them for the GGUF arms.

| ID | Rule | Role |
| --- | --- | --- |
| C1 | Speed. A D arm: median s/page at most 0.5 times D0, on the 20 Experiment 37 pages that ran alone (D0 56.62 s, eq01 p2 excluded as model load). A P arm: median s/page at most 0.5 times P0 (40.2 s, the P0 median over its 221 OK pages), with the P-arm median computed on the same 221 pages. The report gives the all-257 median beside it. | decides |
| C2 | The arm has 0 timeouts at 300 s (P0 had 34 of 257). | decides |
| C3 | KaTeX error rate at most 0.01 over `E-maths` and `E-scan`. Changed from 0.05 on 2026-10-06. | decides |
| C4 | Median `E-script` recall at least the baseline median minus 0.05 (D0 0.8889, P0 0.6095). | decides |
| C5 | The operator finds no invented text on the review list (Experiment 37 G3 rule). | decides |
| C6 | Median Dice similarity to the baseline at least 0.90. | information only |
| C7 | Peak memory below 22.2 GiB for D arms (F5). | information only |

**C1 populations.** D0's 56.62 s comes from 19 alone-timed pages of one run and has no variance estimate. This limit applies to the D-arm speed comparison. The thresholds do not change.

**Pass rule.** C1 to C5 all hold for an arm. C6 and C7 inform the decision only.

**Gate changes.** The operator sets gates before the first run. A later change is a dated amendment. It keeps the original rule in the record.

## Procedure

1. Operator approves the install, download, licence and budget gates in `plan.json` (`approvals`). Each stays `false` until then.
2. Operator confirms DR-2 (licence scope). No download starts before it.
3. Install `mlx-vlm` and the llama.cpp conversion tools (`convert_hf_to_gguf.py` at build 11941, with Python `gguf` and `transformers`) into gitignored environments inside this folder. Record each version.
4. Download the 8-bit pins in `gguf_pins` and `mlx_pins`, and the cross-check file. Record each revision and SHA-256. Do not download the diagnostic MLX 16-bit builds yet.
5. Convert dots.mocr to GGUF bf16 plus a bf16 mmproj at build 11941. Keep the bf16 file as the D3 diagnostic. Quantise the language model to Q8_0 (D4). Quantise the official PaddleOCR-VL GGUF to Q8_0 (P4); keep the official file as the P3 diagnostic. Record each SHA-256. A failed conversion stops that arm and is a finding.
6. Run the D4 smoke pages on the `lodrick-the-lafted` Q8_0 file with our bf16 mmproj too, and compare with D4 (OI-9).
7. Add the `runtime` block with the real hashes and the pinned server flags. Run `verify_llamacpp_runtime` on each GGUF arm. Close the open items that need no OCR run (OI-1, OI-2, OI-5, OI-6, OI-7).
8. Run the parity check on the smoke pages (`eq01` p2 and p3) for each 8-bit arm (see "Preprocessing parity"). Compare the image token grids with the baseline. Fix a flag and update the `runtime` block if a grid differs. Stop an arm whose build ignores `--image-min-tokens` or `--image-max-tokens` (OI-10). (Superseded for D4 and P4 by DR-5, 2026-10-30; see the note under "Preprocessing parity".)
9. Freeze `plan.json` and record its SHA-256 in `tasks.md` (task 3.9). The freeze comes after the `runtime` block and the pins (task 3.6) and the parity check (task 3.8). A setting changed later is a dated amendment.
10. Run a two-page smoke test (`eq01` p2 and p3) for each 8-bit arm. Compare with the scratch figures. Stop an arm whose output is empty.
11. Run each 8-bit arm alone, through `E-maths`, `E-scan` and `E-script`. Use the checkpoint and resume rules in `run_rules`.
12. If a speed-up is at least 1.5 times and below 3 times, run `T-control` for that baseline (20 pages alone, seed 41).
13. Score KaTeX, recall and similarity for every 8-bit arm. List every formula that changed against the baseline.
14. Build the review page for each 8-bit arm: the 10 lowest-similarity pages, every page the noise screen flags, and 5 random pages (seed 41; DR-3). Follow `references/review-page-pattern.md`.
15. Operator reviews. Apply the gates.
16. For each 8-bit arm that fails C3, C4 or C5, run its 16-bit diagnostic on the pages of the failed gate. Download the MLX 16-bit build first if needed (model download approval covers it). Score the failed gate only.
17. Write `report.md`, `output/summary.json` and the verdict.

## Interpretation rules

- A GGUF arm that passes C1 to C5 supports a follow-up OpenSpec change for that engine. It changes no default by itself.
- An MLX arm that passes supports a report only. It does not support a runtime change.
- A GGUF arm that fails at conversion or load is a finding. The engine keeps its shipped backend.
- A 16-bit diagnostic result explains a failure. It never turns a failed 8-bit arm into a pass.
- A speed gain that disappears under `T-control` is a baseline artefact.
- Formula differences are findings. The report lists them even when every gate passes.
- Each result applies to this Mac and these 257 pages. It says nothing about other hardware.

## Runtime budget (estimate)

The estimate covers the 4 scored 8-bit arms, with conversion and model load. The operator sets `runtime_budget_h` in `plan.json`.

- Roughly 2 to 8 hours of machine time in total, if both engines speed up as the scratch figures suggest.
- Basis, dots.mocr: Experiment 37 took 3.31 h at baseline speed. Two dots.mocr arms with no speed-up take about 6.6 h.
- Basis, PaddleOCR-VL: P0 took 6.06 h. The scratch MLX test (2026-10-05) gave 6.6 s and 9.4 s per page, which is about 0.5 to 0.7 h for 257 pages. That test covered two pages only.
- Worst case, with no speed-up on any arm: about 6.6 h for the two dots.mocr arms plus up to 6.1 h for each of the two P arms (12.2 h), roughly 18.8 h or more.
- Each triggered 16-bit diagnostic adds about 20 to 60 minutes. Diagnostics are extra.
- The GGUF arms and the MLX arms are timed separately.
- No cap is set in this plan.

## Approvals and licence

`approvals` in `plan.json` holds four gates. The operator approved all four on 2026-10-30, with DR-2 accepted and a run budget of 19 h.

1. **Install.** `mlx-vlm` and the llama.cpp conversion tools. The approval covers both.
2. **Downloads.** About 9.3 GB up front: dots.mocr MLX 8-bit 4.4 GB; PaddleOCR-VL MLX 8-bit 1.1 GB; official PaddleOCR-VL GGUF and mmproj 1.8 GB; `lodrick-the-lafted` Q8_0 1.9 GB (cross-check). Only if a diagnostic triggers: dots.mocr MLX bf16 6.1 GB, PaddleOCR-VL MLX 16-bit 1.8 GB. The dots.mocr source weights are already in the shared model cache. Conversions add about 8.5 GB. The target is `OMRS_OCR_MODEL_CACHE`.
3. **Licence.** The dots.mocr agreement covers derivative works (clause 3.3). This plan proposes (DR-2) that the check covers:
   - our own GGUF conversion of dots.mocr, which is a derivative work;
   - `mlx-community/dots.mocr-8bit` (same weights as the pinned revision, fact 1);
   - `mlx-community/dots.mocr-bf16` (decided 2026-10-06; diagnostic only);
   - `lodrick-the-lafted/dots.mocr-gguf`, used only as a cross-check.
   The operator decides before any download. PaddleOCR-VL and the OpenGryd builds are Apache-2.0.
4. **Run budget.** The operator sets `runtime_budget_h` and sets `approved`.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan |
| `experiment.json` | the record (status, finding) |
| `output/` (gitignored) | per-arm Markdown, state files and run records |
| `run_ocr.py` | one runner with `--backend {mlx,llamacpp}`; status inside it (`--status`) |
| `summarise.py` | per-arm gate values into `output/summary.json` |
| `analysis.py` | similarity scoring |
| `output/summary.json` | per-arm gate values (committed) |
| `report.md` | verdict, arm table, formula list, the operator's review |

The Standard size allows 3 scripts, so the folder holds `run_ocr.py`, `summarise.py` and `analysis.py` only. Reuse `score_recall.py` and `check_katex.mjs` from Experiment 37 by path (`../omrs-v3/experiments/37-dots-mocr-routing-acceptance-2026-09-30/`). Do not copy them.

## Open items

These items stay open until the operator or a run closes them. Each one is also in `plan.json` (`open_items`).

- **OI-1 (closed 2026-10-30).** `layout.py` in `ocr-workers/engines/dots-mocr/src/omrs_ocr_dots_mocr/` imports only `json`, `re` and `typing` (lines 20-24). The package `__init__.py` imports nothing else. It needs no PyTorch.
- **OI-2.** The llama.cpp converter accepts dots.mocr (fact 2). Confirm that build 11941 loads our conversion and gives non-empty output on the smoke pages.
- **OI-3 (closed 2026-10-30).** The official PaddleOCR-VL GGUF is 16-bit. The Hub header metadata gives architecture `paddleocr` and 466,654,208 parameters. At 2 bytes each that is 933.3 MB, against a file size of 935,769,056 bytes. Confirm the tensor type again at download.
- **OI-4.** Confirm that the installed `mlx-vlm` loads the OpenGryd PaddleOCR-VL 1.6 builds and that PaddleOCR's `mlx-vlm-server` backend accepts them.
- **OI-5.** The PaddleOCR-VL MLX arm reuses the engine's page-subset code (TDR-027) without editing the engine folder.
- **OI-6.** Confirm that the memory sampler covers the llama-server process as well as the client.
- **OI-7.** The Experiment 37 source files sit in `../omrs-v3`. Check their hashes before use.
- **OI-8.** The install approval must cover the llama.cpp conversion tools (Python `gguf` and `transformers`), not only `mlx-vlm`.
- **OI-9.** Cross-check: D4 output on the smoke pages matches the `lodrick-the-lafted` Q8_0 output, with the same bf16 mmproj. A difference is reported and investigated before the D4 run.
- **OI-10.** Suspected risks. (a) The conversion at llama.cpp build 11941 may fail or load wrongly. PR 17575 covers dots.ocr, and the `lodrick-the-lafted` GGUF suggests that dots.mocr works on some build. Build 11941 is not shown. (b) A bf16 mmproj may run slowly on Metal. (c) Build 11941 may ignore `--image-min-tokens` or `--image-max-tokens`. The parity check catches this. The arm then stops and a finding is recorded. The tolerance is not loosened. The smoke tests catch (a) and (b). A failure is a finding and stops that arm only.
- **OI-11 (closed).** P0's effective pipeline version is `v1.6` by the PaddleOCR default (`paddleocr_vl.py`, line 26). Experiment 37 used paddleocr 3.7.0 and paddlex 3.7.2. P0's cap is 4096 per block request and its block limits are 112,896 and 1,003,520 pixels (see "Token cap rule" and "Preprocessing parity").
